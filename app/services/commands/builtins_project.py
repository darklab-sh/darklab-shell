"""Project workspace built-in command handlers."""

from __future__ import annotations

from typing import cast

from core.database_access import get_db_connect
from services.commands.builtins_format import format_native_record, output_line
from services.commands.registry import split_command_argv
from services.projects.active import clear_active_project, get_active_project, set_active_project
from services.projects.contracts import ProjectWorkspaceError
from services.projects.crud import create_project, delete_project, update_project
from services.projects.links import link_project_entity, unlink_project_entity
from services.projects.queries import list_projects
from services.projects.targets import (
    add_project_target,
    delete_project_target,
    infer_project_target_payload,
    list_project_targets,
)


def _project_usage() -> list[dict[str, object]]:
    return [
        output_line("Project commands:", "builtin-section"),
        output_line("  project list [--all]", "builtin-help-row"),
        output_line("  project create <name>", "builtin-help-row"),
        output_line("  project use <name-or-id>", "builtin-help-row"),
        output_line("  project rename <name-or-id> <new-name>", "builtin-help-row"),
        output_line("  project current", "builtin-help-row"),
        output_line("  project clear", "builtin-help-row"),
        output_line("  project archive <name-or-id>", "builtin-help-row"),
        output_line("  project unarchive <name-or-id>", "builtin-help-row"),
        output_line("  project delete <name-or-id>", "builtin-help-row"),
        output_line("  project link last", "builtin-help-row"),
        output_line("  project link run <run-id>", "builtin-help-row"),
        output_line("  project unlink run <run-id>", "builtin-help-row"),
        output_line("  project target list", "builtin-help-row"),
        output_line("  project target add <type> <value>", "builtin-help-row"),
        output_line("  project target quick-add <text-or-value>", "builtin-help-row"),
        output_line("  project target remove <id-or-value>", "builtin-help-row"),
    ]


def _project_display_name(project: dict[str, object]) -> str:
    name = str(project.get("name") or "")
    slug = str(project.get("slug") or "")
    project_id = str(project.get("id") or "")
    return f"{name} ({slug}, {project_id})"


def _project_rows(session_id: str, *, include_archived: bool = False) -> list[dict[str, object]]:
    return [
        cast(dict[str, object], project)
        for project in list_projects(session_id, include_archived=include_archived)
        if project
    ]


def _project_target_rows(session_id: str, project_id: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    offset = 0
    while True:
        page = list_project_targets(session_id, project_id, limit=200, offset=offset)
        if not isinstance(page, dict):
            return rows
        targets = [cast(dict[str, object], target) for target in page.get("targets", []) if target]
        rows.extend(targets)
        offset += len(targets)
        if not targets or offset >= int(page.get("total") or len(rows)):
            return rows


def _resolve_project_ref(
    session_id: str,
    raw_ref: str,
    *,
    include_archived: bool = False,
) -> dict[str, object] | None:
    ref = raw_ref.strip()
    if not ref:
        raise ProjectWorkspaceError("project reference is required")
    ref_lower = ref.lower()
    projects = _project_rows(session_id, include_archived=include_archived)
    id_or_slug_matches = [
        project for project in projects
        if str(project.get("id") or "") == ref or str(project.get("slug") or "").lower() == ref_lower
    ]
    if id_or_slug_matches:
        return id_or_slug_matches[0]
    name_matches = [
        project for project in projects
        if str(project.get("name") or "").lower() == ref_lower
    ]
    if len(name_matches) > 1:
        slugs = ", ".join(str(project.get("slug") or "") for project in name_matches)
        raise ProjectWorkspaceError(f"project name is ambiguous; use one of these slugs: {slugs}")
    return name_matches[0] if name_matches else None


def _latest_run_id(session_id: str, *, tab_id: str = "") -> str:
    with get_db_connect()() as conn:
        if tab_id:
            row = conn.execute(
                "SELECT id FROM runs "
                "WHERE session_id = ? AND run_kind = 'external' AND owner_tab_id = ? "
                "ORDER BY started DESC LIMIT 1",
                (session_id, tab_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM runs "
                "WHERE session_id = ? AND run_kind = 'external' "
                "ORDER BY started DESC LIMIT 1",
                (session_id,),
            ).fetchone()
    return str(row["id"] or "") if row else ""


def _project_link_payload(parts: list[str], session_id: str, *, tab_id: str = "") -> tuple[str, str]:
    if len(parts) >= 3 and (
        parts[2].lower() == "last"
        or (len(parts) >= 4 and parts[2].lower() == "run" and parts[3].lower() == "last")
    ):
        run_id = _latest_run_id(session_id, tab_id=tab_id)
        if not run_id:
            scope = " in this tab" if tab_id else ""
            raise ProjectWorkspaceError(f"no recent run is available to link{scope}")
        return "run", run_id
    if len(parts) < 4:
        raise ProjectWorkspaceError("usage: project link|unlink run <run-id>")
    entity_label = parts[2].lower()
    entity_id = " ".join(parts[3:]).strip()
    entity_map = {
        "run": "run",
    }
    entity_type = entity_map.get(entity_label)
    if not entity_type:
        raise ProjectWorkspaceError("project links support run")
    if not entity_id:
        raise ProjectWorkspaceError("project link run id is required")
    return entity_type, entity_id


def _resolve_project_target_ref(session_id: str, project_id: str, raw_ref: str) -> dict[str, object] | None:
    ref = raw_ref.strip()
    if not ref:
        raise ProjectWorkspaceError("target reference is required")
    targets = _project_target_rows(session_id, project_id)
    for target in targets:
        if str(target.get("id") or "") == ref or str(target.get("value") or "") == ref:
            return target
    return None


def _project_target_lines(session_id: str, project: dict[str, object]) -> list[dict[str, object]]:
    targets = _project_target_rows(session_id, str(project["id"]))
    if not targets:
        return [output_line("project: no targets yet", "builtin-note")]
    lines = [output_line("Project targets:", "builtin-section")]
    lines.append(output_line(f"{'type':<8} value", "builtin-table-header"))
    for target in targets:
        label = str(target.get("label") or "")
        suffix = f"  {label}" if label else ""
        lines.append(output_line(
            f"{str(target.get('type') or ''):<8} {str(target.get('value') or '')}{suffix}",
            "builtin-table-row",
        ))
    return lines


def _run_project_target_command(parts: list[str], session_id: str) -> list[dict[str, object]]:
    project = get_active_project(session_id)
    if not project:
        return [output_line("project: no active project; run `project use <name-or-id>` first")]
    project = cast(dict[str, object], project)
    action = parts[2].lower() if len(parts) > 2 else "list"
    project_id = str(project["id"])
    if action in {"list", "ls"}:
        return _project_target_lines(session_id, project)
    if action == "add":
        if len(parts) < 5:
            return [output_line("Usage: project target add <type> <value>")]
        target = add_project_target(session_id, project_id, {
            "type": parts[3],
            "value": " ".join(parts[4:]).strip(),
        })
        if not target:
            return [output_line("project: active project was not found")]
        target = cast(dict[str, object], target)
        return [output_line(
            f"project: target added {str(target.get('type') or '')} {str(target.get('value') or '')}",
            "builtin-success",
        )]
    if action in {"quick-add", "quick"}:
        text = " ".join(parts[3:]).strip()
        if not text:
            return [output_line("Usage: project target quick-add <text-or-value>")]
        payload = infer_project_target_payload({"text": text, "value": text})
        target = add_project_target(session_id, project_id, payload)
        if not target:
            return [output_line("project: active project was not found")]
        target = cast(dict[str, object], target)
        return [output_line(
            f"project: target added {str(target.get('type') or '')} {str(target.get('value') or '')}",
            "builtin-success",
        )]
    if action in {"remove", "rm", "delete"}:
        ref = " ".join(parts[3:]).strip()
        target = _resolve_project_target_ref(session_id, project_id, ref)
        if not target:
            return [output_line(f"project: target not found: {ref}")]
        removed = delete_project_target(session_id, project_id, str(target["id"]))
        return [output_line(
            f"project: target removed {str(target.get('value') or ref)}",
            "builtin-success" if removed else "builtin-note",
        )]
    return [output_line(f"project: unknown target action '{action}'")]


def run_builtin_project(command: str, session_id: str, *, tab_id: str = "") -> list[dict[str, object]]:
    parts = split_command_argv(command)
    subcommand = parts[1].lower() if len(parts) > 1 else "current"
    try:
        if subcommand in {"help", "-h", "--help"}:
            return _project_usage()
        if subcommand in {"list", "ls"}:
            include_archived = any(part in {"--all", "-a"} for part in parts[2:])
            projects = _project_rows(session_id, include_archived=include_archived)
            active = get_active_project(session_id)
            active_id = str(cast(dict[str, object], active).get("id") or "") if active else ""
            if not projects:
                return [output_line("No projects yet. Run `project create <name>` to start one.", "builtin-note")]
            lines = [output_line("Projects:", "builtin-section")]
            lines.append(output_line(f"  {'slug':<24}  {'status':<8}  name", "builtin-table-header"))
            for project in projects:
                marker = "*" if str(project.get("id") or "") == active_id else " "
                status = str(project.get("status") or "")
                lines.append(output_line(
                    f"{marker} {str(project.get('slug') or ''):<24}  {status:<8}  {str(project.get('name') or '')}",
                    "builtin-table-row",
                ))
            return lines
        if subcommand == "create":
            name = " ".join(parts[2:]).strip()
            if not name:
                return [output_line("Usage: project create <name>")]
            project = create_project(session_id, {"name": name})
            if not project:
                return [output_line("project: could not create project")]
            project = cast(dict[str, object], project)
            set_active_project(session_id, str(project["id"]))
            return [
                output_line(f"project: created {_project_display_name(project)}", "builtin-success"),
                output_line("project: set as active project", "builtin-success"),
            ]
        if subcommand == "current":
            project = get_active_project(session_id)
            if not project:
                return [output_line(
                    "No active project. Run `project use <name-or-id>` or `project create <name>`.",
                    "builtin-note",
                )]
            project = cast(dict[str, object], project)
            return [
                output_line("Active project:", "builtin-section"),
                output_line(format_native_record("name", str(project.get("name") or ""), 11), "builtin-kv"),
                output_line(format_native_record("slug", str(project.get("slug") or ""), 11), "builtin-kv"),
                output_line(format_native_record("id", str(project.get("id") or ""), 11), "builtin-kv"),
            ]
        if subcommand == "use":
            ref = " ".join(parts[2:]).strip()
            project = _resolve_project_ref(session_id, ref)
            if not project:
                return [output_line(f"project: not found: {ref}")]
            active = set_active_project(session_id, str(project["id"]))
            if not active:
                return [output_line(f"project: not found: {ref}")]
            active = cast(dict[str, object], active)
            return [output_line(f"project: active project is {_project_display_name(active)}", "builtin-success")]
        if subcommand == "rename":
            if len(parts) < 4:
                return [output_line("Usage: project rename <name-or-id> <new-name>")]
            ref = parts[2].strip()
            new_name = " ".join(parts[3:]).strip()
            if not ref or not new_name:
                return [output_line("Usage: project rename <name-or-id> <new-name>")]
            project = _resolve_project_ref(session_id, ref, include_archived=True)
            if not project:
                return [output_line(f"project: not found: {ref}")]
            renamed = update_project(session_id, str(project["id"]), {"name": new_name})
            if not renamed:
                return [output_line(f"project: not found: {ref}")]
            renamed = cast(dict[str, object], renamed)
            return [output_line(f"project: renamed {_project_display_name(renamed)}", "builtin-success")]
        if subcommand == "clear":
            cleared = clear_active_project(session_id)
            return [output_line(
                "project: active project cleared" if cleared else "project: no active project was set",
                "builtin-success" if cleared else "builtin-note",
            )]
        if subcommand == "archive":
            ref = " ".join(parts[2:]).strip()
            project = _resolve_project_ref(session_id, ref, include_archived=True)
            if not project:
                return [output_line(f"project: not found: {ref}")]
            active = get_active_project(session_id)
            archived = update_project(session_id, str(project["id"]), {"status": "archived"})
            if active and str(cast(dict[str, object], active).get("id") or "") == str(project["id"]):
                clear_active_project(session_id)
            display_project = cast(dict[str, object], archived) if archived else project
            return [output_line(f"project: archived {_project_display_name(display_project)}", "builtin-success")]
        if subcommand == "unarchive":
            ref = " ".join(parts[2:]).strip()
            project = _resolve_project_ref(session_id, ref, include_archived=True)
            if not project:
                return [output_line(f"project: not found: {ref}")]
            unarchived = update_project(session_id, str(project["id"]), {"status": "active"})
            display_project = cast(dict[str, object], unarchived) if unarchived else project
            return [output_line(f"project: unarchived {_project_display_name(display_project)}", "builtin-success")]
        if subcommand in {"delete", "rm", "remove"}:
            ref = " ".join(parts[2:]).strip()
            project = _resolve_project_ref(session_id, ref, include_archived=True)
            if not project:
                return [output_line(f"project: not found: {ref}")]
            deleted = delete_project(session_id, str(project["id"]))
            return [output_line(
                f"project: deleted {_project_display_name(project)}" if deleted else f"project: not found: {ref}",
                "builtin-success" if deleted else "builtin-note",
            )]
        if subcommand in {"target", "targets"}:
            return _run_project_target_command(parts, session_id)
        if subcommand in {"link", "unlink"}:
            project = get_active_project(session_id)
            if not project:
                return [output_line("project: no active project; run `project use <name-or-id>` first")]
            project = cast(dict[str, object], project)
            entity_type, entity_id = _project_link_payload(parts, session_id, tab_id=tab_id)
            payload = {"entity_type": entity_type, "entity_id": entity_id, "source": "manual"}
            if subcommand == "link":
                link = link_project_entity(session_id, str(project["id"]), payload)
                if not link:
                    return [output_line("project: active project was not found")]
                return [output_line(
                    f"project: linked {entity_type} {entity_id} to {str(project.get('slug') or '')}",
                    "builtin-success",
                )]
            removed = unlink_project_entity(session_id, str(project["id"]), payload)
            message = (
                f"project: unlinked {entity_type} {entity_id}"
                if removed
                else f"project: no link found for {entity_type} {entity_id}"
            )
            return [output_line(
                message,
                "builtin-success" if removed else "builtin-note",
            )]
    except ProjectWorkspaceError as exc:
        return [output_line(f"project: {exc}")]
    return [
        output_line(f"project: unknown subcommand '{subcommand}'"),
        *_project_usage(),
    ]
