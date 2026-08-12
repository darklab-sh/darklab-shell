# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Schema inventory helpers for the SQLite/Postgres unification work."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import sqlite3
from typing import Any, Iterable, Mapping

from core.database_backend import (
    DatabaseBackend,
    sqlite_fts_virtual_table_names,
    sqlite_schema_objects,
    sqlite_table_names,
)
from services.shared_schema import SHARED_TABLES

UNIFIED_BASELINE_APP_TABLES: tuple[str, ...] = (
    "ai_run_assists",
    "ai_suggestion_validations",
    "atlas_entity_import_links",
    "atlas_finding_import_occurrences",
    "atlas_import_batches",
    "atlas_import_drafts",
    "audit_events",
    "entities",
    "entity_intel_snapshots",
    "entity_labels",
    "entity_notes",
    "entity_run_links",
    "evidence_packages",
    "finding_triage_details",
    "findings",
    "findings_occurrences",
    "notification_channels",
    "notification_events",
    "project_auto_promote_rules",
    "project_digest_settings",
    "project_links",
    "project_reports",
    "projects",
    "recent_values",
    "run_file_artifacts",
    "run_output_artifacts",
    "run_output_summary",
    "run_output_summary_status",
    "runs",
    "schedule_fires",
    "schedules",
    "scan_target_observations",
    "secrets",
    "session_preferences",
    "session_tokens",
    "session_variables",
    "snapshots",
    "starred_commands",
    "team_invites",
    "team_members",
    "team_recovery_codes",
    "teams",
    "user_workflows",
    "watcher_fires",
    "watchers",
)

SHARED_APP_TABLES: tuple[str, ...] = (
    *UNIFIED_BASELINE_APP_TABLES,
    *SHARED_TABLES,
    "atlas_import_evidence",
    "workflow_execution_children",
    "workflow_execution_steps",
    "workflow_executions",
    "zap_connector_jobs",
    "oast_correlations",
    "oast_interactions",
)
SQLITE_BACKEND_ARTIFACTS: tuple[str, ...] = (
    "runs_fts",
    "runs_fts_config",
    "runs_fts_data",
    "runs_fts_docsize",
    "runs_fts_idx",
    "runs_ai",
    "runs_ad",
)

POSTGRES_BACKEND_ARTIFACTS: tuple[str, ...] = (
    "schema_migrations",
    "pg_trgm",
)


@dataclass(frozen=True)
class SchemaTableInventory:
    name: str
    columns: Mapping[str, str] = field(default_factory=dict)
    constraints: tuple[str, ...] = ()
    create_sql: str = ""


@dataclass(frozen=True)
class SchemaObjectInventory:
    name: str
    table_name: str
    sql: str
    kind: str


@dataclass(frozen=True)
class SchemaInventory:
    backend: DatabaseBackend
    tables: Mapping[str, SchemaTableInventory]
    indexes: Mapping[str, SchemaObjectInventory]
    triggers: Mapping[str, SchemaObjectInventory]
    functions: Mapping[str, SchemaObjectInventory] = field(default_factory=dict)
    extensions: tuple[str, ...] = ()
    fts_artifacts: tuple[str, ...] = ()

    def missing_shared_tables(self) -> tuple[str, ...]:
        return tuple(sorted(set(SHARED_APP_TABLES) - set(self.tables)))


@dataclass(frozen=True)
class SchemaManifest:
    # table -> {column name -> raw column definition}; the raw definition is normalized
    # to a `ColumnShape` at comparison time so SQLite and Postgres heads can be matched.
    tables: Mapping[str, Mapping[str, str]]
    constraints: Mapping[str, tuple[str, ...]]
    indexes: tuple[str, ...]
    triggers: tuple[str, ...]
    backend_artifacts: Mapping[DatabaseBackend, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class SchemaDrift:
    kind: str
    name: str
    detail: str


@dataclass(frozen=True)
class ColumnShape:
    """Backend-neutral column shape used to compare SQLite and Postgres heads.

    SQLite's dynamic typing collapses Postgres `BOOLEAN`/`JSONB`/`TIMESTAMPTZ` onto
    `INTEGER`/`TEXT`, so exact type strings can never match across backends. We compare
    a coarse type *family* (what SQLite can actually distinguish) plus nullability and a
    canonicalized default — the parts that are meaningful and comparable on both backends.
    Primary-key membership is intentionally excluded: SQLite's `PRAGMA table_info` reports
    a composite table-level `PRIMARY KEY (a, b)` as inline on every member column, while
    the Postgres migration keeps it a table constraint, so column-level PK comparison is a
    false positive. PK integrity is compared at the table-constraint level instead.
    """

    type_family: str
    not_null: bool
    default: str


# Coarse affinity buckets. Anything SQLite stores as the same affinity maps together
# (Postgres BOOLEAN -> integer, JSONB/TIMESTAMPTZ/UUID -> text), so a genuine
# family mismatch (e.g. Postgres BIGINT vs SQLite TEXT) is caught while the
# unavoidable bool/int and json/text ambiguity is tolerated.
_TYPE_FAMILY_EXACT = {
    "int": "integer", "integer": "integer", "bigint": "integer", "smallint": "integer",
    "int2": "integer", "int4": "integer", "int8": "integer", "serial": "integer",
    "bigserial": "integer", "boolean": "integer", "bool": "integer",
    "real": "real", "float": "real", "double": "real", "numeric": "real", "decimal": "real",
    "blob": "blob", "bytea": "blob",
    "text": "text", "varchar": "text", "char": "text", "character": "text", "clob": "text",
    "json": "text", "jsonb": "text", "uuid": "text",
    "timestamp": "text", "timestamptz": "text", "date": "text", "time": "text",
}

_COLUMN_MODIFIER_RE = re.compile(
    r"\b(NOT\s+NULL|DEFAULT|PRIMARY\s+KEY|UNIQUE|CHECK|REFERENCES|COLLATE|GENERATED)\b",
    re.IGNORECASE,
)
_COLUMN_DEFAULT_RE = re.compile(
    r"\bDEFAULT\b\s+(.+?)"
    r"(?:\s+(?:NOT\s+NULL|PRIMARY\s+KEY|UNIQUE|CHECK|REFERENCES|COLLATE|GENERATED)\b|$)",
    re.IGNORECASE | re.DOTALL,
)


def _canonical_default(raw: str) -> str:
    value = normalize_schema_sql(raw).strip().rstrip(",").strip()
    value = re.sub(r"::[A-Za-z0-9_ \"]+", "", value).strip()  # drop Postgres ::type casts
    lowered = value.lower()
    if lowered == "false":
        return "0"
    if lowered == "true":
        return "1"
    return value


def _column_type_family(type_part: str) -> str:
    base = normalize_schema_sql(type_part).lower()
    base = re.sub(r"\(.*?\)", "", base).strip()  # drop varchar(255) / numeric(10,2)
    if not base:
        return ""
    if base in _TYPE_FAMILY_EXACT:
        return _TYPE_FAMILY_EXACT[base]
    first = base.split()[0]
    return _TYPE_FAMILY_EXACT.get(first, first)


def normalize_column_definition(definition: str) -> ColumnShape:
    text = normalize_schema_sql(definition)
    not_null = " NOT NULL " in f" {text.upper()} "
    default_match = _COLUMN_DEFAULT_RE.search(text)
    default = _canonical_default(default_match.group(1)) if default_match else ""
    modifier = _COLUMN_MODIFIER_RE.search(text)
    type_part = text[: modifier.start()] if modifier else text
    return ColumnShape(
        type_family=_column_type_family(type_part),
        not_null=not_null,
        default=default,
    )


def _format_column_shape(shape: ColumnShape) -> str:
    parts = [shape.type_family or "?"]
    if shape.not_null:
        parts.append("not-null")
    if shape.default:
        parts.append(f"default={shape.default}")
    return " ".join(parts)


def schema_manifest_from_inventory(
    inventory: SchemaInventory,
    *,
    tables: Iterable[str] = SHARED_APP_TABLES,
    index_names: Iterable[str] | None = None,
    trigger_names: Iterable[str] | None = None,
) -> SchemaManifest:
    table_names = tuple(tables)
    selected_indexes = tuple(sorted(index_names if index_names is not None else _shared_index_names(inventory)))
    selected_triggers = tuple(sorted(trigger_names if trigger_names is not None else _shared_trigger_names(inventory)))
    return SchemaManifest(
        tables={
            name: dict(inventory.tables.get(name, SchemaTableInventory(name=name)).columns)
            for name in table_names
        },
        constraints={
            name: tuple(sorted(inventory.tables.get(name, SchemaTableInventory(name=name)).constraints))
            for name in table_names
        },
        indexes=selected_indexes,
        triggers=selected_triggers,
        backend_artifacts={
            DatabaseBackend.SQLITE: SQLITE_BACKEND_ARTIFACTS,
            DatabaseBackend.POSTGRES: POSTGRES_BACKEND_ARTIFACTS,
        },
    )


def compare_inventory_to_manifest(
    inventory: SchemaInventory,
    manifest: SchemaManifest,
    *,
    check_shapes: bool = False,
    flag_extras: bool = False,
) -> tuple[SchemaDrift, ...]:
    """Compare a backend inventory against the shared head manifest.

    Defaults are the conservative, missing-only checks used by the runtime stamping guard
    (`verify_sqlite_head_or_raise`): a live database is rejected only when it is genuinely
    behind head (missing tables/columns/constraints/indexes/triggers/artifacts), never for
    a harmless extra column or a benign default difference on an existing database.

    `check_shapes` additionally compares the normalized `ColumnShape` (type family,
    nullability, default) of columns present on both sides, so a column that exists but has
    the wrong type/nullability/default is flagged. `flag_extras` additionally reports
    tables/columns present in the inventory but absent from the shared head. Enable both for
    the CI drift guard (`strict_head_drift`), where the two authored heads must match
    exactly in both directions.
    """
    drifts: list[SchemaDrift] = []
    actual_tables = set(inventory.tables)
    for table_name, expected_columns in sorted(manifest.tables.items()):
        if table_name not in actual_tables:
            drifts.append(SchemaDrift("missing_table", table_name, "expected shared app table is absent"))
            continue
        actual_columns = dict(inventory.tables[table_name].columns)
        expected_names = set(expected_columns)
        actual_names = set(actual_columns)
        for column_name in sorted(expected_names - actual_names):
            drifts.append(SchemaDrift(
                "missing_column",
                f"{table_name}.{column_name}",
                "expected shared app column is absent",
            ))
        if flag_extras:
            for column_name in sorted(actual_names - expected_names):
                drifts.append(SchemaDrift(
                    "extra_column",
                    f"{table_name}.{column_name}",
                    "column is present on this backend but not in the shared head",
                ))
        if check_shapes:
            for column_name in sorted(expected_names & actual_names):
                expected_shape = normalize_column_definition(expected_columns[column_name])
                actual_shape = normalize_column_definition(actual_columns[column_name])
                if expected_shape != actual_shape:
                    drifts.append(SchemaDrift(
                        "column_shape",
                        f"{table_name}.{column_name}",
                        "column shape differs: expected "
                        f"{_format_column_shape(expected_shape)}, found {_format_column_shape(actual_shape)}",
                    ))
        actual_constraints = set(inventory.tables[table_name].constraints)
        for constraint in sorted(set(manifest.constraints.get(table_name, ())) - actual_constraints):
            drifts.append(SchemaDrift(
                "missing_constraint",
                f"{table_name}:{constraint}",
                "expected shared app constraint is absent",
            ))
    if flag_extras:
        allowed = (
            set(manifest.tables)
            | set(SQLITE_BACKEND_ARTIFACTS)
            | set(POSTGRES_BACKEND_ARTIFACTS)
        )
        for table_name in sorted(actual_tables - allowed):
            if table_name.startswith("sqlite_"):
                continue
            drifts.append(SchemaDrift(
                "extra_table",
                table_name,
                "table is present on this backend but not in the shared head or backend-artifact allowlist",
            ))
    for index_name in sorted(set(manifest.indexes) - set(inventory.indexes)):
        drifts.append(SchemaDrift("missing_index", index_name, "expected shared app index is absent"))
    for trigger_name in sorted(set(manifest.triggers) - set(inventory.triggers)):
        drifts.append(SchemaDrift("missing_trigger", trigger_name, "expected shared app trigger is absent"))
    for artifact_name in sorted(
            set(manifest.backend_artifacts.get(inventory.backend, ())) - _inventory_artifact_names(inventory)
        ):
        drifts.append(SchemaDrift(
            "missing_backend_artifact",
            artifact_name,
            f"expected {inventory.backend.value} schema artifact is absent",
        ))
    return tuple(drifts)


def strict_head_drift(
    inventory: SchemaInventory,
    *,
    migrations: tuple[Any, ...] | None = None,
) -> tuple[SchemaDrift, ...]:
    """Bidirectional, shape-aware comparison of a backend head against the shared head.

    This is the CI drift guard: it fails if either backend's head diverges from the shared
    manifest by a missing/extra table or column or a differing column shape.
    """
    return compare_inventory_to_manifest(
        inventory,
        current_head_schema_manifest(migrations=migrations),
        check_shapes=True,
        flag_extras=True,
    )


_WHITESPACE_RE = re.compile(r"\s+")
_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>\"[^\"]+\"|[A-Za-z_][A-Za-z0-9_]*)\s*\(",
    re.IGNORECASE,
)
_CREATE_INDEX_RE = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?P<name>\"[^\"]+\"|[A-Za-z_][A-Za-z0-9_]*)\s+ON\s+"
    r"(?P<table>\"[^\"]+\"|[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
_CREATE_TRIGGER_RE = re.compile(
    r"CREATE\s+TRIGGER\s+(?P<name>\"[^\"]+\"|[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
_CREATE_FUNCTION_RE = re.compile(
    r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+(?P<name>\"[^\"]+\"|[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
_CREATE_EXTENSION_RE = re.compile(
    r"CREATE\s+EXTENSION\s+IF\s+NOT\s+EXISTS\s+(?P<name>\"[^\"]+\"|[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
_ALTER_ADD_COLUMN_RE = re.compile(
    r"ALTER\s+TABLE\s+(?P<table>\"[^\"]+\"|[A-Za-z_][A-Za-z0-9_]*)\s+"
    r"ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?P<column>\"[^\"]+\"|[A-Za-z_][A-Za-z0-9_]*)\s+(?P<definition>.+)",
    re.IGNORECASE | re.DOTALL,
)
_ALTER_ADD_CONSTRAINT_RE = re.compile(
    r"ALTER\s+TABLE\s+(?P<table>\"[^\"]+\"|[A-Za-z_][A-Za-z0-9_]*)\s+"
    r"ADD\s+CONSTRAINT\s+(?P<name>\"[^\"]+\"|[A-Za-z_][A-Za-z0-9_]*)\s+(?P<definition>.+?)(?:;|$)",
    re.IGNORECASE | re.DOTALL,
)
_ALTER_ADD_TABLE_CONSTRAINT_RE = re.compile(
    r"ALTER\s+TABLE\s+(?P<table>\"[^\"]+\"|[A-Za-z_][A-Za-z0-9_]*)\s+"
    r"ADD\s+(?P<definition>PRIMARY\s+KEY\s*\(.+?\)|UNIQUE\s*\(.+?\)|CHECK\s*\(.+?\)|FOREIGN\s+KEY\s*\(.+?\).+?)(?:;|$)",
    re.IGNORECASE | re.DOTALL,
)
_ALTER_DROP_CONSTRAINT_RE = re.compile(
    r"ALTER\s+TABLE\s+(?P<table>\"[^\"]+\"|[A-Za-z_][A-Za-z0-9_]*)\s+"
    r"DROP\s+CONSTRAINT\s+(?:IF\s+EXISTS\s+)?(?P<name>\"[^\"]+\"|[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
_CONSTRAINT_NAME_RE = re.compile(
    r"^CONSTRAINT\s+(?:\"[^\"]+\"|[A-Za-z_][A-Za-z0-9_]*)\s+",
    re.IGNORECASE,
)
_TABLE_CONSTRAINT_KEYWORDS = {"PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "CONSTRAINT"}


def normalize_schema_sql(sql: str | None) -> str:
    return _WHITESPACE_RE.sub(" ", str(sql or "")).strip()


def normalize_constraint_sql(sql: str | None) -> str:
    normalized = normalize_schema_sql(sql)
    normalized = _CONSTRAINT_NAME_RE.sub("", normalized)
    normalized = re.sub(r"\(\s+", "(", normalized)
    normalized = re.sub(r"\s+\)", ")", normalized)
    normalized = re.sub(r"\s*,\s*", ", ", normalized)
    return normalized


def sqlite_head_schema_inventory(conn: Any) -> SchemaInventory:
    objects = [dict(row) for row in sqlite_schema_objects(conn)]
    tables: dict[str, SchemaTableInventory] = {}
    indexes: dict[str, SchemaObjectInventory] = {}
    triggers: dict[str, SchemaObjectInventory] = {}

    for table_name in sqlite_table_names(conn):
        sql = _object_sql(objects, table_name, "table")
        tables[table_name] = SchemaTableInventory(
            name=table_name,
            columns=_sqlite_column_definitions(conn, table_name),
            constraints=_constraints_from_create_table_sql(sql),
            create_sql=normalize_schema_sql(sql),
        )

    for item in objects:
        name = _row_text(item, "name")
        kind = _row_text(item, "type")
        table_name = _row_text(item, "tbl_name")
        sql = normalize_schema_sql(_row_text(item, "sql"))
        if kind == "index" and not name.startswith("sqlite_autoindex"):
            indexes[name] = SchemaObjectInventory(name=name, table_name=table_name, sql=sql, kind=kind)
        elif kind == "trigger":
            triggers[name] = SchemaObjectInventory(name=name, table_name=table_name, sql=sql, kind=kind)

    fts_tables = sqlite_fts_virtual_table_names(conn)
    fts_artifact_names = {
        name
        for name in tables
        if any(name == fts or name.startswith(f"{fts}_") for fts in fts_tables)
    }
    fts_artifact_names.update(
        name
        for name, trigger in triggers.items()
        if any(fts in trigger.sql for fts in fts_tables)
    )
    fts_artifacts = tuple(sorted(fts_artifact_names))
    return SchemaInventory(
        backend=DatabaseBackend.SQLITE,
        tables=dict(sorted(tables.items())),
        indexes=dict(sorted(indexes.items())),
        triggers=dict(sorted(triggers.items())),
        fts_artifacts=fts_artifacts,
    )


def postgres_migration_schema_inventory(statements: list[str] | tuple[str, ...]) -> SchemaInventory:
    tables: dict[str, SchemaTableInventory] = {}
    indexes: dict[str, SchemaObjectInventory] = {}
    triggers: dict[str, SchemaObjectInventory] = {}
    functions: dict[str, SchemaObjectInventory] = {}
    extensions: set[str] = set()

    for raw_statement in statements:
        statement = str(raw_statement or "")
        normalized = normalize_schema_sql(statement)
        if not normalized:
            continue
        drop_constraint_match = _ALTER_DROP_CONSTRAINT_RE.search(normalized)
        if drop_constraint_match:
            table_name = _clean_identifier(drop_constraint_match.group("table"))
            constraint_name = _clean_identifier(drop_constraint_match.group("name"))
            existing = tables.get(table_name)
            if existing is not None:
                tables[table_name] = SchemaTableInventory(
                    name=table_name,
                    columns=existing.columns,
                    constraints=tuple(
                        constraint
                        for constraint in existing.constraints
                        if not _constraint_matches_drop(table_name, constraint_name, constraint)
                    ),
                    create_sql=existing.create_sql,
                )
        parsed_table = _parse_create_table_statement(statement)
        if parsed_table is not None:
            tables[parsed_table.name] = parsed_table
            continue
        column_match = _ALTER_ADD_COLUMN_RE.search(normalized)
        if column_match:
            table_name = _clean_identifier(column_match.group("table"))
            column_name = _clean_identifier(column_match.group("column"))
            definition = normalize_schema_sql(column_match.group("definition").rstrip(";"))
            existing = tables.get(table_name, SchemaTableInventory(name=table_name))
            tables[table_name] = SchemaTableInventory(
                name=table_name,
                columns={**dict(existing.columns), column_name: definition},
                constraints=existing.constraints,
                create_sql=existing.create_sql,
            )
            continue
        constraint_match = _ALTER_ADD_CONSTRAINT_RE.search(normalized)
        if constraint_match:
            table_name = _clean_identifier(constraint_match.group("table"))
            constraint_name = _clean_identifier(constraint_match.group("name"))
            definition = normalize_schema_sql(constraint_match.group("definition").rstrip(";"))
            existing = tables.get(table_name, SchemaTableInventory(name=table_name))
            tables[table_name] = SchemaTableInventory(
                name=table_name,
                columns=existing.columns,
                constraints=tuple(sorted({
                    *existing.constraints,
                    normalize_constraint_sql(f"CONSTRAINT {constraint_name} {definition}"),
                })),
                create_sql=existing.create_sql,
            )
            continue
        table_constraint_match = _ALTER_ADD_TABLE_CONSTRAINT_RE.search(normalized)
        if table_constraint_match:
            table_name = _clean_identifier(table_constraint_match.group("table"))
            definition = normalize_constraint_sql(table_constraint_match.group("definition").rstrip(";"))
            existing = tables.get(table_name, SchemaTableInventory(name=table_name))
            tables[table_name] = SchemaTableInventory(
                name=table_name,
                columns=existing.columns,
                constraints=tuple(sorted({*existing.constraints, definition})),
                create_sql=existing.create_sql,
            )
            continue
        index_match = _CREATE_INDEX_RE.search(normalized)
        if index_match:
            name = _clean_identifier(index_match.group("name"))
            table_name = _clean_identifier(index_match.group("table"))
            indexes[name] = SchemaObjectInventory(name=name, table_name=table_name, sql=normalized, kind="index")
            continue
        trigger_match = _CREATE_TRIGGER_RE.search(normalized)
        if trigger_match:
            name = _clean_identifier(trigger_match.group("name"))
            triggers[name] = SchemaObjectInventory(name=name, table_name="", sql=normalized, kind="trigger")
            continue
        function_match = _CREATE_FUNCTION_RE.search(normalized)
        if function_match:
            name = _clean_identifier(function_match.group("name"))
            functions[name] = SchemaObjectInventory(name=name, table_name="", sql=normalized, kind="function")
            continue
        extension_match = _CREATE_EXTENSION_RE.search(normalized)
        if extension_match:
            extensions.add(_clean_identifier(extension_match.group("name")))

    return SchemaInventory(
        backend=DatabaseBackend.POSTGRES,
        tables=dict(sorted(tables.items())),
        indexes=dict(sorted(indexes.items())),
        triggers=dict(sorted(triggers.items())),
        functions=dict(sorted(functions.items())),
        extensions=tuple(sorted(extensions)),
    )


def _migrations_after_unified_baseline(migrations: tuple[Any, ...]) -> tuple[Any, ...]:
    baseline_indexes = [
        index for index, migration in enumerate(migrations)
        if getattr(migration, "baseline_apply", None) is not None
    ]
    if not baseline_indexes:
        return migrations
    return migrations[baseline_indexes[-1] + 1:]


def _app_migrations() -> tuple[Any, ...]:
    from core.migrations import MIGRATIONS  # noqa: PLC0415

    return MIGRATIONS


def current_sqlite_migration_schema_inventory(
    migrations: tuple[Any, ...] | None = None,
) -> SchemaInventory:
    """Build the current SQLite head from the frozen baseline plus post-baseline migrations."""
    from core.database_backend import DatabaseBackend  # noqa: PLC0415
    from core.migrations.baseline import apply_sqlite_baseline  # noqa: PLC0415

    selected = _app_migrations() if migrations is None else migrations
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        apply_sqlite_baseline(conn)
        for migration in _migrations_after_unified_baseline(selected):
            for statement in migration.statements_for(DatabaseBackend.SQLITE):
                conn.execute(statement)
        return sqlite_head_schema_inventory(conn)
    finally:
        conn.close()


def current_postgres_baseline_schema_inventory() -> SchemaInventory:
    """Build the current Postgres head inventory rendered from the frozen baseline source."""
    from core.migrations.baseline import postgres_baseline_statements

    return postgres_migration_schema_inventory(postgres_baseline_statements())


def current_postgres_migration_schema_inventory(
    migrations: tuple[Any, ...] | None = None,
) -> SchemaInventory:
    """Build the current Postgres head from the frozen baseline plus post-baseline migrations."""
    from core.database_backend import DatabaseBackend  # noqa: PLC0415
    from core.migrations.baseline import postgres_baseline_statements  # noqa: PLC0415

    selected = _app_migrations() if migrations is None else migrations
    statements = [
        *postgres_baseline_statements(),
        *(
            statement
            for migration in _migrations_after_unified_baseline(selected)
            for statement in migration.statements_for(DatabaseBackend.POSTGRES)
        ),
    ]
    return postgres_migration_schema_inventory(tuple(statements))


def current_head_schema_manifest(migrations: tuple[Any, ...] | None = None) -> SchemaManifest:
    """Return the canonical shared-app manifest for the current schema head."""
    return schema_manifest_from_inventory(current_sqlite_migration_schema_inventory(migrations=migrations))


def postgres_head_schema_inventory(conn: Any) -> SchemaInventory:
    """Inspect the live Postgres app schema for reconciliation verification."""
    table_rows = conn.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_type = 'BASE TABLE'
        """
    ).fetchall()
    table_names = sorted(str(row["table_name"]) for row in table_rows)
    column_rows = conn.execute(
        """
        SELECT table_name, column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = current_schema()
        ORDER BY table_name, ordinal_position
        """
    ).fetchall()
    columns_by_table: dict[str, dict[str, str]] = {table_name: {} for table_name in table_names}
    for row in column_rows:
        table_name = str(row["table_name"])
        if table_name not in columns_by_table:
            continue
        columns_by_table[table_name][str(row["column_name"])] = normalize_schema_sql(str(row["data_type"] or ""))

    index_rows = conn.execute(
        """
        SELECT schemaname, tablename, indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = current_schema()
        """
    ).fetchall()
    indexes = {
        str(row["indexname"]): SchemaObjectInventory(
            name=str(row["indexname"]),
            table_name=str(row["tablename"]),
            sql=normalize_schema_sql(str(row["indexdef"] or "")),
            kind="index",
        )
        for row in index_rows
    }
    trigger_rows = conn.execute(
        """
        SELECT trigger_name, event_object_table AS table_name
        FROM information_schema.triggers
        WHERE trigger_schema = current_schema()
        """
    ).fetchall()
    triggers = {
        str(row["trigger_name"]): SchemaObjectInventory(
            name=str(row["trigger_name"]),
            table_name=str(row["table_name"]),
            sql="",
            kind="trigger",
        )
        for row in trigger_rows
    }
    extension_rows = conn.execute("SELECT extname FROM pg_extension").fetchall()
    return SchemaInventory(
        backend=DatabaseBackend.POSTGRES,
        tables={
            table_name: SchemaTableInventory(name=table_name, columns=columns_by_table.get(table_name, {}))
            for table_name in table_names
        },
        indexes=dict(sorted(indexes.items())),
        triggers=dict(sorted(triggers.items())),
        extensions=tuple(sorted(str(row["extname"]) for row in extension_rows)),
    )


def verify_postgres_head_schema(conn: Any) -> tuple[SchemaDrift, ...]:
    manifest = current_head_schema_manifest()
    runtime_manifest = SchemaManifest(
        tables=manifest.tables,
        constraints={},
        indexes=manifest.indexes,
        triggers=manifest.triggers,
        backend_artifacts=manifest.backend_artifacts,
    )
    return compare_inventory_to_manifest(postgres_head_schema_inventory(conn), runtime_manifest)


def verify_inventory_matches_current_head(inventory: SchemaInventory) -> tuple[SchemaDrift, ...]:
    return compare_inventory_to_manifest(inventory, current_head_schema_manifest())


def verify_sqlite_head_schema(conn: Any) -> tuple[SchemaDrift, ...]:
    return verify_inventory_matches_current_head(sqlite_head_schema_inventory(conn))


def _sqlite_column_definitions(conn: Any, table_name: str) -> dict[str, str]:
    rows = conn.execute(f"PRAGMA table_info({_quote_sqlite_identifier(table_name)})").fetchall()
    columns: dict[str, str] = {}
    for row in rows:
        name = str(row[1])
        column_type = str(row[2] or "")
        not_null = " NOT NULL" if int(row[3] or 0) else ""
        default = "" if row[4] is None else f" DEFAULT {row[4]}"
        primary_key = " PRIMARY KEY" if int(row[5] or 0) else ""
        columns[name] = normalize_schema_sql(f"{column_type}{not_null}{default}{primary_key}")
    return dict(sorted(columns.items()))


def _parse_create_table_statement(statement: str) -> SchemaTableInventory | None:
    match = _CREATE_TABLE_RE.search(statement)
    if not match:
        return None
    table_name = _clean_identifier(match.group("name"))
    open_index = statement.find("(", match.start())
    close_index = _matching_paren_index(statement, open_index)
    if open_index < 0 or close_index < 0:
        return None
    columns: dict[str, str] = {}
    constraints: list[str] = []
    for item in _split_top_level_items(statement[open_index + 1:close_index]):
        first = _first_token(item)
        if not first:
            continue
        if first.upper() in _TABLE_CONSTRAINT_KEYWORDS:
            constraints.append(normalize_constraint_sql(item))
            continue
        columns[_clean_identifier(first)] = normalize_schema_sql(item[len(first):].strip())
    return SchemaTableInventory(
        name=table_name,
        columns=dict(sorted(columns.items())),
        constraints=tuple(sorted(constraints)),
        create_sql=normalize_schema_sql(statement),
    )


def _constraints_from_create_table_sql(sql: str | None) -> tuple[str, ...]:
    if not sql:
        return ()
    parsed = _parse_create_table_statement(sql)
    return parsed.constraints if parsed else ()


def _split_top_level_items(body: str) -> list[str]:
    items: list[str] = []
    start = 0
    depth = 0
    in_single_quote = False
    index = 0
    while index < len(body):
        char = body[index]
        if char == "'" and (index == 0 or body[index - 1] != "\\"):
            in_single_quote = not in_single_quote
        elif not in_single_quote:
            if char == "(":
                depth += 1
            elif char == ")":
                depth = max(0, depth - 1)
            elif char == "," and depth == 0:
                items.append(body[start:index].strip())
                start = index + 1
        index += 1
    tail = body[start:].strip()
    if tail:
        items.append(tail)
    return items


def _matching_paren_index(text: str, open_index: int) -> int:
    if open_index < 0:
        return -1
    depth = 0
    in_single_quote = False
    for index in range(open_index, len(text)):
        char = text[index]
        if char == "'" and (index == 0 or text[index - 1] != "\\"):
            in_single_quote = not in_single_quote
            continue
        if in_single_quote:
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _first_token(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    if stripped.startswith('"'):
        end = stripped.find('"', 1)
        return stripped[:end + 1] if end >= 0 else stripped
    return stripped.split(maxsplit=1)[0]


def _object_sql(objects: list[dict[str, Any]], name: str, kind: str) -> str:
    for item in objects:
        if _row_text(item, "name") == name and _row_text(item, "type") == kind:
            return _row_text(item, "sql")
    return ""


def _row_text(row: Mapping[str, Any], key: str) -> str:
    return str(row.get(key) or "")


def _clean_identifier(identifier: str) -> str:
    value = str(identifier or "").strip().rstrip(";")
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value


def _quote_sqlite_identifier(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _constraint_matches_drop(table_name: str, constraint_name: str, constraint: str) -> bool:
    normalized_name = constraint_name.lower()
    normalized_constraint = constraint.lower()
    if f"constraint {normalized_name} " in normalized_constraint:
        return True
    table_prefix = f"{table_name.lower()}_"
    local_name = normalized_name[len(table_prefix):] if normalized_name.startswith(table_prefix) else normalized_name
    if local_name.endswith("_check"):
        column_name = local_name[:-6]
        return normalized_constraint.startswith("check ") and f"{column_name} in" in normalized_constraint
    if local_name.endswith("_key"):
        column_name = local_name[:-4]
        return normalized_constraint.startswith("unique ") and f"({column_name})" in normalized_constraint
    if local_name == "pkey":
        return normalized_constraint.startswith("primary key")
    return False


def _shared_index_names(inventory: SchemaInventory) -> tuple[str, ...]:
    return tuple(
        sorted(
            name
            for name, index in inventory.indexes.items()
            if index.table_name in SHARED_APP_TABLES
            and not name.startswith("sqlite_autoindex")
            and not name.endswith(("_trgm",))
        )
    )


def _shared_trigger_names(inventory: SchemaInventory) -> tuple[str, ...]:
    return tuple(
        sorted(
            name
            for name, trigger in inventory.triggers.items()
            if name not in SQLITE_BACKEND_ARTIFACTS
            and (trigger.table_name in SHARED_APP_TABLES or name in {"findings_legacy_ai", "findings_ad"})
        )
    )


def _inventory_artifact_names(inventory: SchemaInventory) -> set[str]:
    artifacts = {*inventory.fts_artifacts, *inventory.extensions}
    if inventory.backend == DatabaseBackend.POSTGRES:
        artifacts.add("schema_migrations")
    return artifacts
