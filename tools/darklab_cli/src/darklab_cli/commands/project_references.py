# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Resolve active Project slugs and stable ids for CLI command families."""

from __future__ import annotations

import re

from ..client import DarklabClient, DarklabCliError

_PROJECT_ID_RE = re.compile(r"^prj_[A-Za-z0-9_-]{1,64}$")


def resolve_active_project_id(client: DarklabClient, project_ref: object) -> str:
    reference = str(project_ref or "").strip()
    if _PROJECT_ID_RE.fullmatch(reference):
        return reference
    offset = 0
    while True:
        payload = client.request("GET", "/projects", params={"limit": 100, "offset": offset})
        projects = payload.get("projects") if isinstance(payload, dict) else []
        if not isinstance(projects, list):
            break
        for project in projects:
            if not isinstance(project, dict):
                continue
            if (
                str(project.get("status") or "").casefold() == "active"
                and str(project.get("slug") or "").casefold() == reference.casefold()
            ):
                project_id = str(project.get("id") or "")
                if _PROJECT_ID_RE.fullmatch(project_id):
                    return project_id
        offset += len(projects)
        if not payload.get("has_more") or not projects:
            break
    raise DarklabCliError(f"active Project slug not found: {reference}")


__all__ = ["resolve_active_project_id"]
