"""
Project slug allocation helpers.
"""

from __future__ import annotations

import re
import secrets


def slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return (slug or "project")[:80].strip("-") or "project"


def allocate_slug(conn, session_id, name, *, project_id=None, team_id=""):
    base = slugify(name)
    for index in range(0, 100):
        suffix = "" if index == 0 else f"-{index + 1}"
        candidate = f"{base[:80 - len(suffix)]}{suffix}"
        if team_id:
            row = conn.execute(
                "SELECT id FROM projects WHERE team_id = ? AND slug = ?",
                (team_id, candidate),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM projects "
                "WHERE (team_id IS NULL OR team_id = '') AND session_id = ? AND slug = ?",
                (session_id, candidate),
            ).fetchone()
        if not row or row["id"] == project_id:
            return candidate
    return f"{base[:61]}-{secrets.token_hex(4)}"
