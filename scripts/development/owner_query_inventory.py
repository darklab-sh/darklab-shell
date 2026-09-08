#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Generate and verify the reviewed legacy ownership-query inventory."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Iterable, cast


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INVENTORY = REPO_ROOT / ".tooling" / "owner-query-inventory.jsonl"
SCANNED_ROOTS = (REPO_ROOT / "app", REPO_ROOT / "scripts")
EXCLUDED_PATHS = {
    "app/services/teams/ownership_queries.py",
    "scripts/development/owner_query_inventory.py",
}
REVIEWED_FIELDS = (
    "tables",
    "table_team_columns",
    "current_result_set",
    "conversion_classification",
    "planned_branch",
    "phase_3b_replacement",
    "reviewed_exception",
)
QUERY_HELPERS = (
    "personal_scope_predicate",
    "shared_owner_predicate",
    "personal_only_owner_predicate",
    "team_capable_owner_predicate",
    "token_keyed_owner_predicate",
    "composite_owner_predicate",
    "attribution_values",
)
OWNER_COLUMN_RE = re.compile(
    r"(?i)\b(?:[a-z_][a-z0-9_]*\.)?"
    r"(?:session_id|session_token|session_hash|token_hash|team_id|principal_id|personal_workspace_id|credential_id|"
    r"[a-z_][a-z0-9_]*(?:_session_id|_session_token|_session_hash|_token_hash|_team_id|_principal_id|_workspace_id|_credential_id))"
    r"\s+(?:=|!=|<>|\bIS\b|\bIN\b|\bLIKE\b)"
)
TABLE_RE = re.compile(
    r"(?i)\b(?:FROM|JOIN|UPDATE|INSERT\s+INTO|DELETE\s+FROM|INDEX(?:\s+IF\s+NOT\s+EXISTS)?\s+\S+\s+ON)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)"
)
OPERATION_RE = re.compile(r"(?i)\b(SELECT|UPDATE|DELETE|INSERT|UPSERT|CREATE)\b")
CONDITION_COLUMN_RE = re.compile(
    r"(?i)\b(?:[a-z_][a-z0-9_]*\.)?"
    r"(session_id|session_token|session_hash|token_hash|team_id|principal_id|personal_workspace_id|credential_id|"
    r"[a-z_][a-z0-9_]*(?:_session_id|_session_token|_session_hash|_token_hash|_team_id|_principal_id|_workspace_id|_credential_id))"
    r"\s+(?:=|!=|<>|\bIS\b|\bIN\b|\bLIKE\b)"
)
BOUND_COLUMN_RE = re.compile(
    r"(?i)\b(?:[a-z_][a-z0-9_]*\.)?([a-z_][a-z0-9_]*)\s+"
    r"(?:=|\bIN\b)\s*(?:\?|%s|\{[^}]+\})"
)


@dataclass(frozen=True)
class InventorySite:
    site_id: str
    path: str
    line: int
    scope: str
    tables: tuple[str, ...]
    operation: str
    key_shape: str
    bound_key_columns: tuple[str, ...]
    adapter_shape: str
    predicate_team_behavior: str
    table_team_columns: dict[str, str]
    current_result_set: str
    conversion_classification: str
    planned_branch: str
    phase_3b_replacement: str
    reviewed_exception: str
    source: str


def _stringish(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                try:
                    rendered = ast.unparse(value.value)
                except Exception:
                    rendered = "expression"
                parts.append("{" + rendered + "}")
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _stringish(node.left)
        right = _stringish(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _is_stringish_parent(node: ast.AST | None) -> bool:
    return isinstance(node, (ast.Constant, ast.JoinedStr, ast.BinOp)) and _stringish(node) is not None


def _normalized_source(value: str) -> str:
    return " ".join(value.split())


def _predicate_slice(value: str) -> str:
    normalized = _normalized_source(value)
    marker_positions = [
        match.start()
        for match in re.finditer(r"(?i)\b(?:WHERE|ON|HAVING)\b", normalized)
    ]
    if marker_positions:
        return normalized[min(marker_positions) :]
    if OPERATION_RE.search(normalized):
        return ""
    return normalized


def _scope_for(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    names: list[str] = []
    current = parents.get(node)
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(current.name)
        current = parents.get(current)
    return ".".join(reversed(names)) or "<module>"


def _operation(value: str) -> str:
    match = OPERATION_RE.search(value)
    return match.group(1).lower() if match else "predicate_fragment"


def _tables(value: str) -> tuple[str, ...]:
    tables = {
        match.group(1).lower()
        for match in TABLE_RE.finditer(value)
        if match.group(1).lower() != "set"
    }
    return tuple(sorted(tables)) or ("<caller-selected>",)


def _key_shape(columns: Iterable[str], bound_columns: Iterable[str]) -> str:
    normalized = tuple(column.lower() for column in columns)
    owner_columns = {
        column
        for column in normalized
        if column.endswith("session_id")
        or column.endswith("session_token")
        or column.endswith("session_hash")
        or column.endswith("token_hash")
        or column.endswith("principal_id")
        or column.endswith("workspace_id")
        or column.endswith("credential_id")
    }
    has_token = any(column.endswith("session_token") for column in owner_columns)
    has_token_hash = any(column.endswith("token_hash") for column in owner_columns)
    has_session_hash = any(column.endswith("session_hash") for column in owner_columns)
    has_session = any(column.endswith("session_id") for column in owner_columns)
    has_principal = any(
        column.endswith(("principal_id", "workspace_id", "credential_id"))
        for column in owner_columns
    )
    if has_token:
        base = "session-token"
    elif has_token_hash:
        base = "token-hash"
    elif has_session_hash:
        base = "session-hash"
    elif has_session:
        base = "session-id"
    elif has_principal:
        base = "principal-era"
    else:
        base = "team-only"
    attribution = any(
        marker in column
        for column in owner_columns
        for marker in ("created_by_", "updated_by_", "changed_by_", "actor_", "requested_by_")
    )
    if attribution:
        return "attribution-only"
    extra_keys = sorted(
        {
            column.lower()
            for column in bound_columns
            if not column.lower().endswith(
                (
                    "session_id",
                    "session_token",
                    "session_hash",
                    "token_hash",
                    "team_id",
                    "principal_id",
                    "workspace_id",
                    "credential_id",
                )
            )
        }
    )
    return "+".join((base, *extra_keys)) if extra_keys else base


def _team_behavior(value: str) -> str:
    normalized = _normalized_source(value)
    if re.search(
        r"(?i)COALESCE\(\s*(?:[a-z_][a-z0-9_]*\.)?team_id\s*,\s*''\s*\)\s*=\s*''",
        normalized,
    ):
        return "null-or-empty"
    if re.search(
        r"(?i)team_id\s+IS\s+NULL\s+OR\s+(?:[a-z_][a-z0-9_]*\.)?team_id\s*=\s*''",
        normalized,
    ):
        return "null-or-empty"
    if re.search(r"(?i)team_id\s+IS\s+NULL", normalized):
        return "null"
    if re.search(r"(?i)team_id\s*=\s*''", normalized):
        return "empty"
    if re.search(r"(?i)team_id\s*=\s*(?:\?|%s|\{[^}]+\})", normalized):
        return "bound-team"
    if re.search(r"(?i)team_id\s*(?:=|!=|<>|\bIS\b|\bIN\b|\bLIKE\b)", normalized):
        return "other-team-expression"
    return "unfiltered"


def _adapter_shape(key_shape: str, team_behavior: str) -> str:
    if key_shape == "attribution-only":
        return "attribution-only"
    if "+" in key_shape:
        return "composite-key"
    if key_shape.startswith(("session-token", "token-hash")):
        return "token-keyed"
    if team_behavior == "unfiltered":
        return "personal-only"
    return "team-capable"


def _current_result_set(key_shape: str, team_behavior: str) -> str:
    if key_shape == "attribution-only":
        return "Records actor metadata; these fields do not establish row ownership."
    if key_shape == "team-only":
        descriptions = {
            "unfiltered": "Rows selected by a team expression outside this fragment.",
            "null": "Rows whose team_id is NULL; no personal owner predicate is present.",
            "empty": "Rows whose team_id is empty; no personal owner predicate is present.",
            "null-or-empty": "Rows whose team_id is NULL or empty; no personal owner predicate is present.",
            "bound-team": "Rows matching the supplied team id.",
            "other-team-expression": "Rows matching the source's explicit team expression.",
        }
        return descriptions[team_behavior]
    if key_shape.startswith("principal-era"):
        owner = "principal-era identifier"
    elif key_shape.startswith(("session-token", "token-hash")):
        owner = "legacy token owner"
    elif key_shape.startswith("session-hash"):
        owner = "legacy hashed session value"
    else:
        owner = "legacy session owner"
    descriptions = {
        "unfiltered": f"Rows matching the {owner}, without a team-column restriction.",
        "null": f"Rows matching the {owner} whose team_id is NULL.",
        "empty": f"Rows matching the {owner} whose team_id is an empty string.",
        "null-or-empty": f"Rows matching the {owner} whose team_id is NULL or empty.",
        "bound-team": "Rows matching the supplied team id; the personal owner key is not necessarily checked.",
        "other-team-expression": "Rows matching the source's explicit team expression and legacy owner conditions.",
    }
    return descriptions[team_behavior]


def _planned_branch(path: str) -> str:
    if "/migrations/" in path or path.endswith("/migration.py"):
        return "migration-code"
    if re.search(r"/(?:history|runs?)/", path) or path.startswith("app/blueprints/history"):
        return "refactor/owner-context-history-runs"
    if re.search(r"/(?:projects|assessments|atlas)/", path) or path.startswith(
        ("app/blueprints/projects", "app/blueprints/atlas")
    ):
        return "refactor/owner-context-projects-assessments-atlas"
    if re.search(r"/(?:workspace|workflows|secrets|session)/", path):
        return "refactor/owner-context-files-workflows-secrets"
    if re.search(r"/(?:scheduler|watchers|notifications|workers|connectors)/", path):
        return "refactor/owner-context-automation-notifications"
    return "refactor/owner-context-remaining-surfaces"


def _phase_3b_replacement(key_shape: str) -> str:
    if key_shape == "attribution-only":
        return "credential_id/member_id attribution fields"
    if key_shape.startswith(("session-token", "token-hash")):
        return "principal_id or personal_workspace_id foreign key; credential id only for attribution"
    if key_shape == "team-only":
        return "team_id"
    return "personal_workspace_id or team_id"


def _classification(path: str) -> str:
    if _planned_branch(path) == "migration-code":
        return "migration"
    if path.startswith("app/services/auth/"):
        return "principal-foundation"
    return "unclassified"


def _reviewed_exception(path: str) -> str:
    if _planned_branch(path) == "migration-code":
        return "migration code"
    if path.startswith("app/services/auth/"):
        return "principal credential persistence boundary"
    return "temporary Phase 3A direct predicate"


def _table_shapes() -> dict[str, str]:
    app_path = str(REPO_ROOT / "app")
    if app_path not in sys.path:
        sys.path.insert(0, app_path)
    from core.schema_manifest import current_postgres_migration_schema_inventory  # noqa: PLC0415

    inventory = current_postgres_migration_schema_inventory()
    result: dict[str, str] = {}
    for name, table in inventory.tables.items():
        definition = table.columns.get("team_id")
        if definition is None:
            result[name] = "absent"
        elif "NOT NULL" in definition.upper() and "DEFAULT ''" in definition.upper():
            result[name] = "not-null-default-empty"
        elif "NOT NULL" in definition.upper():
            result[name] = "not-null"
        else:
            result[name] = "nullable"
    return result


def _iter_python_paths() -> Iterable[Path]:
    for root in SCANNED_ROOTS:
        for path in sorted(root.rglob("*.py")):
            relative = path.relative_to(REPO_ROOT).as_posix()
            if relative in EXCLUDED_PATHS or "__pycache__" in path.parts:
                continue
            yield path


def _production_helper_calls() -> dict[str, int]:
    counts = Counter({name: 0 for name in QUERY_HELPERS})
    helper_modules = {
        "app/services/teams/ownership_queries.py",
        "app/services/teams/scope.py",
    }
    for path in sorted((REPO_ROOT / "app").rglob("*.py")):
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative in helper_modules or "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            else:
                continue
            if name in QUERY_HELPERS:
                counts[name] += 1
    return dict(sorted(counts.items()))


def generate_sites() -> list[InventorySite]:
    table_shapes = _table_shapes()
    sites: list[InventorySite] = []
    for path in _iter_python_paths():
        relative = path.relative_to(REPO_ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=relative)
        except SyntaxError as exc:
            raise RuntimeError(f"Unable to parse {relative}: {exc}") from exc
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        scope_tables: dict[str, set[str]] = {}
        for candidate in ast.walk(tree):
            value = _stringish(candidate)
            if value is None or _is_stringish_parent(parents.get(candidate)):
                continue
            tables = _tables(_normalized_source(value))
            if tables == ("<caller-selected>",):
                continue
            scope_tables.setdefault(_scope_for(candidate, parents), set()).update(tables)
        seen: Counter[tuple[str, str]] = Counter()
        for node in ast.walk(tree):
            value = _stringish(node)
            if value is None or _is_stringish_parent(parents.get(node)):
                continue
            predicate = _predicate_slice(value)
            if not predicate or not OWNER_COLUMN_RE.search(predicate):
                continue
            columns = tuple(match.group(1) for match in CONDITION_COLUMN_RE.finditer(predicate))
            bound_columns = tuple(match.group(1) for match in BOUND_COLUMN_RE.finditer(predicate))
            key_shape = _key_shape(columns, bound_columns)
            team_behavior = _team_behavior(predicate)
            scope = _scope_for(node, parents)
            normalized = _normalized_source(value)
            fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10]
            duplicate_key = (scope, fingerprint)
            seen[duplicate_key] += 1
            suffix = f":{seen[duplicate_key]}" if seen[duplicate_key] > 1 else ""
            site_id = f"{relative}:{scope}:{fingerprint}{suffix}"
            tables = _tables(normalized)
            if tables == ("<caller-selected>",) and scope_tables.get(scope):
                tables = tuple(sorted(scope_tables[scope]))
            sites.append(
                InventorySite(
                    site_id=site_id,
                    path=relative,
                    line=int(getattr(node, "lineno", 0)),
                    scope=scope,
                    tables=tables,
                    operation=_operation(normalized),
                    key_shape=key_shape,
                    bound_key_columns=tuple(sorted(set(bound_columns))),
                    adapter_shape=_adapter_shape(key_shape, team_behavior),
                    predicate_team_behavior=team_behavior,
                    table_team_columns={
                        table: table_shapes.get(table, "unknown") for table in tables
                    },
                    current_result_set=_current_result_set(key_shape, team_behavior),
                    conversion_classification=_classification(relative),
                    planned_branch=_planned_branch(relative),
                    phase_3b_replacement=_phase_3b_replacement(key_shape),
                    reviewed_exception=_reviewed_exception(relative),
                    source=normalized[:500],
                )
            )
    return sorted(sites, key=lambda site: (site.path, site.line, site.site_id))


def _reviewed_sites(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    reviewed: dict[str, dict[str, object]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid inventory JSON on line {line_number}: {exc}") from exc
        if record.get("kind") != "site":
            continue
        site_id = str(record.get("site_id") or "")
        if not site_id or site_id in reviewed:
            raise RuntimeError(f"Invalid or duplicate inventory site id on line {line_number}")
        reviewed[site_id] = record
    return reviewed


def build_inventory(reviewed_sites: dict[str, dict[str, object]] | None = None) -> dict[str, object]:
    sites = [asdict(site) for site in generate_sites()]
    reviewed_sites = reviewed_sites or {}
    for site in sites:
        reviewed = reviewed_sites.get(str(site["site_id"]))
        if reviewed is None:
            continue
        for field in REVIEWED_FIELDS:
            if field in reviewed:
                site[field] = reviewed[field]
    return {
        "format_version": 1,
        "contract": (
            "This reviewed list is the temporary exception boundary for direct legacy ownership "
            "predicates. Personal owner values remain current session identities during Phase 3A."
        ),
        "scan_roots": [path.relative_to(REPO_ROOT).as_posix() for path in SCANNED_ROOTS],
        "excluded_paths": sorted(EXCLUDED_PATHS),
        "summary": {
            "site_count": len(sites),
            "by_adapter_shape": dict(
                sorted(Counter(str(site["adapter_shape"]) for site in sites).items())
            ),
            "by_branch": dict(
                sorted(Counter(str(site["planned_branch"]) for site in sites).items())
            ),
            "by_classification": dict(
                sorted(Counter(str(site["conversion_classification"]) for site in sites).items())
            ),
            "production_helper_calls": _production_helper_calls(),
        },
        "sites": sites,
    }


def _render(inventory: dict[str, object]) -> str:
    metadata = {key: value for key, value in inventory.items() if key != "sites"}
    sites = cast(list[dict[str, object]], inventory["sites"])
    lines = [json.dumps({"kind": "metadata", **metadata}, sort_keys=True)]
    lines.extend(json.dumps({"kind": "site", **site}, sort_keys=True) for site in sites)
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true", help="replace the checked-in inventory")
    action.add_argument("--check", action="store_true", help="fail when the inventory has drifted")
    action.add_argument("--summary", action="store_true", help="print the current scan summary")
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    args = parser.parse_args()

    inventory_path = args.inventory.resolve()
    reviewed_sites = _reviewed_sites(inventory_path)
    inventory = build_inventory(reviewed_sites)
    if args.summary:
        print(json.dumps(inventory["summary"], indent=2))
        return 0
    rendered = _render(inventory)
    if args.write:
        inventory_path.parent.mkdir(parents=True, exist_ok=True)
        inventory_path.write_text(rendered, encoding="utf-8")
        print(f"wrote {inventory_path.relative_to(REPO_ROOT)}")
        return 0
    if not inventory_path.exists():
        print(f"ownership-query inventory is missing: {inventory_path}", file=sys.stderr)
        return 1
    if inventory_path.read_text(encoding="utf-8") != rendered:
        print(
            "ownership-query inventory has drifted; run "
            "python scripts/development/owner_query_inventory.py --write",
            file=sys.stderr,
        )
        return 1
    summary = cast(dict[str, object], inventory["summary"])
    print(f"ownership-query inventory is current ({summary['site_count']} sites)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
