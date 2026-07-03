"""Architecture boundary tests for the Python application layers."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_BLUEPRINT_DIR = _REPO_ROOT / "app" / "blueprints"
_API_V1_SERVICE_DIR = _REPO_ROOT / "app" / "services" / "api_v1"
_API_V1_SERVICE_ALLOWED_FILES = {
    "__init__.py",
    "auth.py",
    "openapi.py",
    "serialization.py",
}


@dataclass(frozen=True)
class BlueprintPersistenceMetrics:
    connection_calls: int = 0
    connection_symbols: int = 0
    execute_calls: int = 0
    core_database_symbols: int = 0
    core_database_backend_symbols: int = 0
    cleanup_helper_symbols: int = 0
    sql_string_fragments: int = 0

    def nonzero(self) -> bool:
        return any(getattr(self, field) for field in self.__dataclass_fields__)


_PERSISTENCE_CLEANUP_HELPERS = {
    "delete_run_artifacts",
    "delete_snapshot_metadata",
}

_PERSISTENCE_EXECUTE_METHODS = {
    "execute",
    "executemany",
    "executescript",
}

_PERSISTENCE_CONNECTION_SYMBOLS = {
    "db_connect",
}

_BLUEPRINT_PERSISTENCE_RATCHET = {}

_SQL_STRING_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"\bSELECT\b.+\bFROM\b",
        r"\bINSERT\s+INTO\b",
        r"\bUPDATE\b.+\bSET\b",
        r"\bDELETE\s+FROM\b",
        r"\bWHERE\b.+(?:=|\bIN\s*\(|\bLIKE\b|\bEXISTS\b|\bAND\b|\bOR\b)",
        r"\bJOIN\b.+\bON\b",
        r"\bORDER\s+BY\b",
        r"\bGROUP\s+BY\b",
        r"\b(?:session_id|team_id)\s*=\s*\?",
    )
)


def _looks_like_sql_string(value: str) -> bool:
    return any(pattern.search(value) for pattern in _SQL_STRING_PATTERNS)


class _BlueprintPersistenceVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.connection_calls = 0
        self.connection_symbols = 0
        self.connection_aliases = set(_PERSISTENCE_CONNECTION_SYMBOLS)
        self.execute_calls = 0
        self.core_database_symbols = 0
        self.core_database_backend_symbols = 0
        self.cleanup_helper_symbols = 0
        self.sql_string_fragments = 0

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in self.connection_aliases:
            self.connection_calls += 1
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr == "db_connect":
                self.connection_calls += 1
            if node.func.attr in _PERSISTENCE_EXECUTE_METHODS:
                self.execute_calls += 1
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "core.database" or alias.name.startswith("core.database."):
                self.core_database_symbols += 1
            if alias.name == "core.database_backend" or alias.name.startswith("core.database_backend."):
                self.core_database_backend_symbols += 1
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name in _PERSISTENCE_CONNECTION_SYMBOLS:
                self.connection_symbols += 1
                self.connection_aliases.add(alias.asname or alias.name)
        if node.module == "core.database":
            self.core_database_symbols += len(node.names)
            self.cleanup_helper_symbols += sum(
                1 for alias in node.names if alias.name in _PERSISTENCE_CLEANUP_HELPERS
            )
        elif node.module == "core.database_backend":
            self.core_database_backend_symbols += len(node.names)
        elif node.module == "core":
            self.core_database_symbols += sum(1 for alias in node.names if alias.name == "database")
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and _looks_like_sql_string(node.value):
            self.sql_string_fragments += 1
        self.generic_visit(node)

    def metrics(self) -> BlueprintPersistenceMetrics:
        return BlueprintPersistenceMetrics(
            connection_calls=self.connection_calls,
            connection_symbols=self.connection_symbols,
            execute_calls=self.execute_calls,
            core_database_symbols=self.core_database_symbols,
            core_database_backend_symbols=self.core_database_backend_symbols,
            cleanup_helper_symbols=self.cleanup_helper_symbols,
            sql_string_fragments=self.sql_string_fragments,
        )


def _blueprint_persistence_metrics(path: Path) -> BlueprintPersistenceMetrics:
    visitor = _BlueprintPersistenceVisitor()
    visitor.visit(ast.parse(path.read_text(), filename=str(path)))
    return visitor.metrics()


def _blueprint_python_files(root: Path = _BLUEPRINT_DIR) -> list[Path]:
    return sorted(root.rglob("*.py"))


def _blueprint_ratcheted_path(path: Path, root: Path = _BLUEPRINT_DIR) -> str:
    return path.relative_to(root).as_posix()


class TestBlueprintPersistenceBoundary:
    def test_blueprint_connection_detection_catches_reexported_aliases(self):
        source = """
from services.example import db_connect as connect

def route():
    with connect() as conn:
        return conn
"""
        visitor = _BlueprintPersistenceVisitor()
        visitor.visit(ast.parse(source))

        assert visitor.metrics().connection_symbols == 1
        assert visitor.metrics().connection_calls == 1

    def test_blueprint_execute_family_detection_covers_bulk_and_scripts(self):
        source = """
def route(conn):
    conn.execute("SELECT 1")
    conn.executemany("INSERT INTO x VALUES (?)", [(1,), (2,)])
    conn.executescript("CREATE TABLE x (id INTEGER)")
"""
        visitor = _BlueprintPersistenceVisitor()
        visitor.visit(ast.parse(source))

        assert visitor.metrics().execute_calls == 3

    def test_blueprint_execute_family_detection_is_conservative_by_design(self):
        source = """
def route(pipeline):
    pipeline.execute()
"""
        visitor = _BlueprintPersistenceVisitor()
        visitor.visit(ast.parse(source))

        assert visitor.metrics().execute_calls == 1

    def test_blueprint_sql_string_detection_catches_owned_fragments(self):
        source = """
def run_owner_clause(prefix, team_id):
    if team_id:
        return f"{prefix}team_id = ?", [team_id]
    return f"{prefix}session_id = ? AND ({prefix}team_id IS NULL OR {prefix}team_id = '')"

def rows(conn):
    return conn.fetch_all("SELECT * FROM runs WHERE session_id = ?")
"""
        visitor = _BlueprintPersistenceVisitor()
        visitor.visit(ast.parse(source))

        assert visitor.metrics().sql_string_fragments == 3

    def test_blueprint_sql_string_detection_ignores_route_text(self):
        source = """
def route(bp):
    bp.route("/history/bulk-delete", methods=["DELETE"])
    return "Delete selected runs from history."
"""
        visitor = _BlueprintPersistenceVisitor()
        visitor.visit(ast.parse(source))

        assert visitor.metrics().sql_string_fragments == 0

    def test_blueprint_scan_recurses_into_subpackages(self, tmp_path):
        blueprint_root = tmp_path / "blueprints"
        nested = blueprint_root / "history" / "queries.py"
        nested.parent.mkdir(parents=True)
        nested.write_text(
            """
def route(conn):
    conn.execute("SELECT 1")
""",
            encoding="utf-8",
        )

        actual = {
            _blueprint_ratcheted_path(path, blueprint_root): metrics
            for path in _blueprint_python_files(blueprint_root)
            if (metrics := _blueprint_persistence_metrics(path)).nonzero()
        }

        assert actual == {
            "history/queries.py": BlueprintPersistenceMetrics(execute_calls=1),
        }

    def test_blueprint_direct_database_access_matches_ratchet(self):
        actual = {
            _blueprint_ratcheted_path(path): metrics
            for path in _blueprint_python_files()
            if (metrics := _blueprint_persistence_metrics(path)).nonzero()
        }

        assert actual == _BLUEPRINT_PERSISTENCE_RATCHET, (
            "Blueprint persistence boundary drift detected. Move new database access "
            "behind services, or lower the ratchet after removing blueprint access.\n"
            f"actual={actual!r}"
        )

    def test_api_v1_service_package_stays_non_persistence(self):
        actual = {path.name for path in _API_V1_SERVICE_DIR.glob("*.py")}

        assert actual == _API_V1_SERVICE_ALLOWED_FILES, (
            "services/api_v1 should stay limited to auth, serialization, and OpenAPI helpers. "
            "Put persistence and database-backed operations in the owning domain service instead.\n"
            f"actual={sorted(actual)!r}"
        )
