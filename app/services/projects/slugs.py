# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Project slug allocation helpers.
"""

from __future__ import annotations

import re
import secrets

from services.teams.ownership_queries import PersonalTeamRows, composite_owner_predicate
from services.teams.scope import owner_context_for_scope


def slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return (slug or "project")[:80].strip("-") or "project"


def allocate_slug(conn, session_id, name, *, project_id=None, team_id=""):
    base = slugify(name)
    for index in range(0, 100):
        suffix = "" if index == 0 else f"-{index + 1}"
        candidate = f"{base[:80 - len(suffix)]}{suffix}"
        owner = composite_owner_predicate(
            owner_context_for_scope(session_id, team_id=team_id),
            key_values=(("slug", candidate),),
            team_column="team_id",
            personal_team_rows=PersonalTeamRows.EMPTY,
        )
        row = conn.execute(
            f"SELECT id FROM projects WHERE {owner.sql}",  # nosec
            owner.params,
        ).fetchone()
        if not row or row["id"] == project_id:
            return candidate
    return f"{base[:61]}-{secrets.token_hex(4)}"
