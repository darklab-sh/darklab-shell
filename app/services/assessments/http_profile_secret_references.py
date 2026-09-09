# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Secret-name and consumer-binding resolution for HTTP profiles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.teams.ownership_queries import token_keyed_owner_predicate

if TYPE_CHECKING:
    from services.teams.scope import OwnerContext


def referenced_secret_names(profile: Mapping[str, Any]) -> set[str]:
    names = {
        str(value)
        for value in profile.get("secret_refs", {}).values()
        if str(value)
    }
    names.update(
        str(header.get("secret_name") or "")
        for header in profile.get("headers", [])
        if isinstance(header, Mapping) and str(header.get("secret_name") or "")
    )
    return names


def available_secret_names(conn: Any, context: OwnerContext) -> set[str]:
    owner = token_keyed_owner_predicate(context, token_column="owner_id")
    rows = conn.execute(f"SELECT name FROM secrets WHERE {owner.sql} ORDER BY name", owner.params).fetchall()  # nosec
    return {str(row["name"] or "") for row in rows}


def secret_reference_lookup(conn: Any, context: OwnerContext) -> dict[str, str]:
    owner = token_keyed_owner_predicate(context, token_column="owner_id")
    rows = conn.execute(f"SELECT name, consumer_envs FROM secrets WHERE {owner.sql} ORDER BY name", owner.params).fetchall()  # nosec
    names = {str(row["name"] or ""): str(row["name"] or "") for row in rows}
    aliases: dict[str, str] = {}
    decode_list = dialect_for_backend(get_db_backend()).decode_json_list
    for row in rows:
        name = str(row["name"] or "")
        for value in decode_list(row["consumer_envs"]):
            aliases.setdefault(str(value or ""), name)
    aliases.update(names)
    return aliases


def canonicalize_secret_references(
    profile: dict[str, Any],
    references: Mapping[str, str],
) -> None:
    profile["secret_refs"] = {
        str(slot): str(references.get(str(name), str(name)))
        for slot, name in profile.get("secret_refs", {}).items()
    }
    profile["headers"] = [
        {
            **dict(header),
            "secret_name": str(
                references.get(
                    str(header.get("secret_name") or ""),
                    str(header.get("secret_name") or ""),
                )
            ),
        }
        for header in profile.get("headers", [])
        if isinstance(header, Mapping)
    ]
