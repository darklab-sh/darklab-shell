"""Session-scoped command variables.

Variables are app-mediated substitutions.  They are not exported to the
subprocess environment; commands are expanded before normal policy validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re

from database import db_connect

VARIABLE_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,31}$")
VARIABLE_REFERENCE_RE = re.compile(r"(?<!\\)\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
VARIABLE_DOLLAR_RE = re.compile(r"(?<!\\)\$")
MAX_VARIABLE_VALUE_LENGTH = 512


@dataclass(frozen=True)
class SessionVariableExpansion:
    command: str
    used_names: tuple[str, ...]


class SessionVariableError(ValueError):
    """Base error for invalid session-variable operations."""


class InvalidSessionVariableName(SessionVariableError):
    def __init__(self, name: str):
        super().__init__(
            f"invalid variable name '{name}'; use [A-Z][A-Z0-9_]{{0,31}}"
        )
        self.name = name


class InvalidSessionVariableValue(SessionVariableError):
    pass


class UndefinedSessionVariable(SessionVariableError):
    def __init__(self, name: str):
        super().__init__(f"undefined session variable: ${name}")
        self.name = name


class InvalidSessionVariableReference(SessionVariableError):
    def __init__(self):
        super().__init__("invalid session variable reference; use $NAME or ${NAME}")


def normalize_variable_name(name: str) -> str:
    normalized = str(name or "").strip()
    if not VARIABLE_NAME_RE.fullmatch(normalized):
        raise InvalidSessionVariableName(normalized)
    return normalized


def validate_variable_value(value: str) -> str:
    normalized = str(value)
    if "\x00" in normalized or "\n" in normalized or "\r" in normalized:
        raise InvalidSessionVariableValue("variable values cannot contain control newlines or NUL bytes")
    if len(normalized) > MAX_VARIABLE_VALUE_LENGTH:
        raise InvalidSessionVariableValue(
            f"variable values cannot exceed {MAX_VARIABLE_VALUE_LENGTH} characters"
        )
    return normalized


def list_session_variables(session_id: str) -> dict[str, str]:
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT name, value FROM session_variables WHERE session_id = ? ORDER BY name",
            (session_id,),
        ).fetchall()
    return {str(row["name"]): str(row["value"]) for row in rows}


def set_session_variable(session_id: str, name: str, value: str) -> None:
    normalized_name = normalize_variable_name(name)
    normalized_value = validate_variable_value(value)
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with db_connect() as conn:
        conn.execute(
            "INSERT INTO session_variables (session_id, name, value, updated) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(session_id, name) DO UPDATE SET value = excluded.value, updated = excluded.updated",
            (session_id, normalized_name, normalized_value, updated),
        )
        conn.commit()


def unset_session_variable(session_id: str, name: str) -> bool:
    normalized_name = normalize_variable_name(name)
    with db_connect() as conn:
        result = conn.execute(
            "DELETE FROM session_variables WHERE session_id = ? AND name = ?",
            (session_id, normalized_name),
        )
        conn.commit()
    return bool(result.rowcount)


def expand_session_variables(command: str, session_id: str) -> SessionVariableExpansion:
    variables = list_session_variables(session_id)
    used: list[str] = []

    for dollar in VARIABLE_DOLLAR_RE.finditer(command):
        if VARIABLE_REFERENCE_RE.match(command, dollar.start()) is None:
            raise InvalidSessionVariableReference()

    def replace(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2) or ""
        if not VARIABLE_NAME_RE.fullmatch(name):
            raise InvalidSessionVariableName(name)
        if name not in variables:
            raise UndefinedSessionVariable(name)
        if name not in used:
            used.append(name)
        return variables[name]

    expanded = VARIABLE_REFERENCE_RE.sub(replace, command)
    return SessionVariableExpansion(expanded, tuple(used))
