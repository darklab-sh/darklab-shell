# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Session file built-in command handlers."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Mapping, Sequence, cast

from config import resolve_effective_cfg
from services.commands.builtins_format import (
    format_bytes,
    format_native_record,
    output_line,
    text_lines,
)
from services.commands.registry import split_command_argv
from services.diff.sources import DiffSourceError, diff_source_notice, resolve_diff_sources
from services.diff.text import DiffMode, format_text_diff
from services.teams.capabilities import Capability, role_can
from services.teams.scope import OwnerContext, owner_context_for_scope
from services.workspace.file_mutations import copy_owner_workspace_file, touch_owner_workspace_file
from services.workspace.files import (
    InvalidWorkspacePath,
    WorkspaceBinaryFile,
    WorkspaceDisabled,
    WorkspaceFileNotFound,
    WorkspacePathNotFound,
    WorkspacePermissionDenied,
    WorkspaceQuotaExceeded,
    expand_owner_workspace_path_pattern,
    list_owner_workspace_directories,
    list_owner_workspace_files,
    move_owner_workspace_path,
    read_owner_workspace_text_file,
    workspace_path_has_glob,
    workspace_settings,
    owner_workspace_usage,
)


def _parse_dt(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _format_clock(value: str | None) -> str:
    if not value:
        return "-"
    dt = _parse_dt(value)
    return dt.astimezone().strftime("%H:%M:%S")


def _workspace_command_error(exc: Exception) -> list[dict[str, object]]:
    if isinstance(exc, WorkspaceDisabled):
        return [output_line("file: workspace file storage is disabled on this instance")]
    if isinstance(exc, WorkspaceFileNotFound):
        return [output_line("file: file was not found")]
    if isinstance(exc, WorkspacePathNotFound):
        return [output_line("file: workspace file or folder was not found")]
    if isinstance(exc, WorkspacePermissionDenied):
        return [output_line(f"file: {exc}")]
    if isinstance(exc, WorkspaceBinaryFile):
        return [output_line(f"file: {exc}")]
    if isinstance(exc, (InvalidWorkspacePath, WorkspaceQuotaExceeded)):
        return [output_line(f"file: {exc}")]
    raise exc


def _workspace_list_rows(
    files: list[dict[str, object]],
    directories: list[dict[str, object]],
    *,
    recursive: bool = False,
    target: str = "",
) -> list[dict[str, object]]:
    normalized_target = "/".join(part for part in str(target or "").split("/") if part)
    target_prefix = f"{normalized_target}/" if normalized_target else ""

    def in_target(path: str) -> bool:
        return not normalized_target or path.startswith(target_prefix)

    def relative_path(path: str) -> str:
        if target_prefix and path.startswith(target_prefix):
            return path[len(target_prefix):]
        return path

    by_parent: dict[str, list[dict[str, object]]] = {}
    directory_paths = {
        str(item["path"]) for item in directories
        if str(item["path"]) != normalized_target and in_target(str(item["path"]))
    }

    for item in files:
        path = str(item["path"])
        if not in_target(path):
            continue
        parent = path.rpartition("/")[0]
        if parent:
            by_parent.setdefault(parent, []).append(item)

        while parent:
            if parent != normalized_target and in_target(parent):
                directory_paths.add(parent)
            parent = parent.rpartition("/")[0]

    rows: list[dict[str, object]] = []
    if not recursive:
        direct_directories: set[str] = set()
        for path in directory_paths:
            relative = relative_path(path)
            if "/" not in relative:
                direct_directories.add(relative)
        for item in files:
            path = str(item["path"])
            if not in_target(path):
                continue
            relative = relative_path(path)
            if "/" not in relative:
                rows.append({"kind": "file", "path": relative, "item": item})
        for relative in sorted(direct_directories):
            rows.append({"kind": "directory", "path": relative, "display": f"{relative}/"})
        return sorted(rows, key=lambda candidate: str(candidate.get("display") or candidate["path"]))

    def add_directory(path: str) -> None:
        display_path = relative_path(path)
        depth = display_path.count("/")
        rows.append({
            "kind": "directory",
            "path": path,
            "display": f"{'  ' * depth}{display_path}/",
        })

        for item in sorted(by_parent.get(path, []), key=lambda candidate: str(candidate["path"])):
            name = str(item["path"]).rsplit("/", 1)[-1]
            rows.append({
                "kind": "file",
                "path": str(item["path"]),
                "display": f"{'  ' * (depth + 1)}{name}",
                "item": item,
            })

        child_prefix = f"{path}/"
        child_directories = sorted(
            candidate for candidate in directory_paths
            if candidate.startswith(child_prefix) and "/" not in candidate[len(child_prefix):]
        )
        for child in child_directories:
            add_directory(child)

    root_directories = sorted(
        path for path in directory_paths
        if "/" not in relative_path(path)
    )
    for directory in root_directories:
        add_directory(directory)

    for item in sorted(by_parent.get(normalized_target, []), key=lambda candidate: str(candidate["path"])):
        rows.append({"kind": "file", "path": str(item["path"]), "item": item})
    return rows


def _workspace_glob_list_rows(
    matches: Sequence[object],
    files: list[dict[str, object]],
) -> list[dict[str, object]]:
    files_by_path = {str(item["path"]): item for item in files}
    rows: list[dict[str, object]] = []
    for match in matches:
        path = str(getattr(match, "path", ""))
        kind = str(getattr(match, "kind", ""))
        if not path:
            continue
        if kind == "directory":
            rows.append({"kind": "directory", "path": path, "display": f"{path}/"})
        elif kind == "file":
            rows.append({"kind": "file", "path": path, "item": files_by_path.get(path, {"path": path, "size": 0})})
    return sorted(rows, key=lambda candidate: str(candidate.get("display") or candidate["path"]))


def _parse_workspace_list_command(parts: list[str]) -> tuple[bool, bool, str, str | None]:
    root = parts[0].lower() if parts else ""
    if root == "file":
        if len(parts) < 2 or parts[1].lower() not in {"list", "ls"}:
            return False, False, "", "Usage: file list [-lR] [folder]"
        args = parts[2:]
        usage = "Usage: file list [-lR] [folder]"
    elif root == "ls":
        args = parts[1:]
        usage = "Usage: ls [-lR] [folder]"
    elif root == "ll":
        args = parts[1:]
        usage = "Usage: ll [-R] [folder]"
    else:
        return False, False, "", "Usage: file list [-lR] [folder]"
    long = root == "ll"
    recursive = False
    targets: list[str] = []
    for arg in args:
        if re.fullmatch(r"-[lR]+", arg):
            long = long or "l" in arg
            recursive = recursive or "R" in arg
        elif arg.startswith("-"):
            return False, False, "", usage
        else:
            targets.append(arg)
    if len(targets) > 1:
        return False, False, "", usage
    return long, recursive, targets[0] if targets else "", None


def parse_workspace_list_command(parts: list[str]) -> tuple[bool, bool, str, str | None]:
    return _parse_workspace_list_command(parts)


_WORKSPACE_DIFF_USAGE = (
    "Usage: file diff [-q|--brief|-u|--unified|-y|--side-by-side] "
    "[--last | <source1> <source2>]"
)


def parse_workspace_diff_command(
    parts: list[str],
) -> tuple[DiffMode, str, str, bool, str | None]:
    root = parts[0].lower() if parts else ""
    if root == "file":
        if len(parts) < 2 or parts[1].lower() != "diff":
            return "normal", "", "", False, _WORKSPACE_DIFF_USAGE
        args = parts[2:]
    elif root == "diff":
        args = parts[1:]
    else:
        return "normal", "", "", False, _WORKSPACE_DIFF_USAGE

    mode: DiffMode = "normal"
    mode_selected = False
    operands: list[str] = []
    use_last = False
    parse_options = True
    options: dict[str, DiffMode] = {
        "-q": "brief",
        "--brief": "brief",
        "-u": "unified",
        "--unified": "unified",
        "-y": "side_by_side",
        "--side-by-side": "side_by_side",
    }
    for arg in args:
        if parse_options and arg == "--":
            parse_options = False
            continue
        if parse_options and arg.startswith("-"):
            if arg == "--last":
                if use_last:
                    return "normal", "", "", False, _WORKSPACE_DIFF_USAGE
                use_last = True
                continue
            selected = options.get(arg)
            if selected is None or (mode_selected and selected != mode):
                return "normal", "", "", False, _WORKSPACE_DIFF_USAGE
            mode = selected
            mode_selected = True
            continue
        operands.append(arg)
    if use_last:
        if operands:
            return "normal", "", "", False, _WORKSPACE_DIFF_USAGE
        return mode, "", "", True, None
    if len(operands) != 2:
        return "normal", "", "", False, _WORKSPACE_DIFF_USAGE
    return mode, operands[0], operands[1], False, None


def run_builtin_diff(
    parts: list[str],
    owner: OwnerContext,
    cfg: Mapping[str, Any],
    *,
    tab_id: str = "",
) -> list[dict[str, object]]:
    mode, left_reference, right_reference, use_last, usage_error = parse_workspace_diff_command(parts)
    if usage_error:
        root = parts[0].lower() if parts else "file"
        return [output_line(usage_error if root == "file" else usage_error.replace("file diff", "diff", 1))]
    try:
        left, right = resolve_diff_sources(
            owner,
            left_reference=left_reference,
            right_reference=right_reference,
            use_last=use_last,
            tab_id=tab_id,
            cfg=cfg,
        )
    except DiffSourceError as exc:
        return [output_line(f"diff: {exc}")]
    except Exception as exc:
        return _workspace_command_error(exc)
    result = format_text_diff(
        left.text,
        right.text,
        left_name=left.label,
        right_name=right.label,
        mode=mode,
    )
    notices = [notice for notice in (diff_source_notice(left), diff_source_notice(right)) if notice]
    return text_lines([*notices, *result.lines])


def _workspace_owner_context(session_id: str, owner_context: OwnerContext | None = None) -> OwnerContext:
    if owner_context is not None:
        return owner_context
    return owner_context_for_scope(session_id)


def _can_manage_workspace_files(owner_context: OwnerContext, team_role: str = "") -> bool:
    if not owner_context.is_team:
        return True
    return role_can(team_role, Capability.MANAGE_WORKSPACE_FILES)


def _workspace_write_denied() -> list[dict[str, object]]:
    return [output_line("file: your team role can view Files but can't change them")]


def _workspace_item_size(item: dict[str, object]) -> int:
    value = item.get("size")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def run_builtin_workspace(
    command: str,
    session_id: str,
    *,
    owner_context: OwnerContext | None = None,
    team_role: str = "",
    tab_id: str = "",
) -> list[dict[str, object]]:
    parts = split_command_argv(command)
    subcommand = parts[1].lower() if len(parts) > 1 else "help"
    owner = _workspace_owner_context(session_id, owner_context)
    cfg = resolve_effective_cfg()

    if subcommand in {"help", "--help", "-h"}:
        return [
            output_line("Session file commands:", "builtin-section"),
            output_line("  file list [-lR] [folder]", "builtin-help-row"),
            output_line("  file ls [-lR] [folder]", "builtin-help-row"),
            output_line("  file show <file>", "builtin-help-row"),
            output_line("  file diff [-q|-u|-y] [--last | <source1> <source2>]", "builtin-help-row"),
            output_line("  file add [file]", "builtin-help-row"),
            output_line("  file edit <file>", "builtin-help-row"),
            output_line("  file download <file>", "builtin-help-row"),
            output_line("  file copy <source> <destination>", "builtin-help-row"),
            output_line("  file move <source> <destination>", "builtin-help-row"),
            output_line("  file touch <file>", "builtin-help-row"),
            output_line("  file rm <file-or-folder>", "builtin-help-row"),
            output_line("", "builtin-spacer"),
            output_line("Aliases:", "builtin-section"),
            output_line("  ls [-lR]    -> file list [-lR]", "builtin-help-row"),
            output_line("  ll [-R]     -> file list -l [-R]", "builtin-help-row"),
            output_line("  cat <file>  -> file show <file>", "builtin-help-row"),
            output_line("  diff <source1> <source2>  -> file diff <source1> <source2>", "builtin-help-row"),
            output_line("  cp <source> <destination>  -> file copy <source> <destination>", "builtin-help-row"),
            output_line("  mv <source> <destination>  -> file move <source> <destination>", "builtin-help-row"),
            output_line("  touch <file>  -> file touch <file>", "builtin-help-row"),
            output_line("  rm <file-or-folder>   -> file rm <file-or-folder>", "builtin-help-row"),
            output_line("", "builtin-spacer"),
            output_line("Output capture:", "builtin-section"),
            output_line("  command > file       overwrite a Files entry without terminal output", "builtin-help-row"),
            output_line("  command >> file      append to a Files entry without terminal output", "builtin-help-row"),
            output_line("  command | tee file   overwrite a Files entry and keep terminal output", "builtin-help-row"),
            output_line("", "builtin-spacer"),
            output_line("Example flow:", "builtin-section"),
            output_line("  Create targets.txt from the Files panel.", "builtin-note"),
            output_line("  Run: nmap -iL targets.txt", "builtin-help-row"),
            output_line("  Run: curl -o response.html https://ip.darklab.sh", "builtin-help-row"),
            output_line("  Diff sources: <file>, file:<file>, or run:<run-id>; --last uses this tab.", "builtin-note"),
        ]

    if subcommand in {"list", "ls"}:
        long, recursive, target, usage_error = _parse_workspace_list_command(parts)
        if usage_error:
            return [output_line(usage_error)]
        try:
            settings = workspace_settings(cfg)
            files = list_owner_workspace_files(owner, cfg)
            directories = list_owner_workspace_directories(owner, cfg)
            usage = owner_workspace_usage(owner, cfg)
        except Exception as exc:
            return _workspace_command_error(exc)

        remaining_bytes = max(0, settings.quota_bytes - usage.bytes_used)
        lines = [
            output_line("Session files:", "builtin-section"),
            output_line(format_native_record("files", f"{usage.file_count}/{settings.max_files}", 11), "builtin-kv"),
            output_line(
                format_native_record(
                    "usage",
                    f"{format_bytes(usage.bytes_used)} / {format_bytes(settings.quota_bytes)}",
                    11,
                ),
                "builtin-kv",
            ),
            output_line(format_native_record("remaining", format_bytes(remaining_bytes), 11), "builtin-kv"),
        ]
        if target and workspace_path_has_glob(target):
            try:
                rows = _workspace_glob_list_rows(
                    expand_owner_workspace_path_pattern(owner, target, cfg),
                    files,
                )
            except Exception as exc:
                return _workspace_command_error(exc)
        else:
            rows = _workspace_list_rows(files, directories, recursive=recursive, target=target)
        if not rows:
            lines.append(output_line(
                "  No matching workspace files." if target else "  No workspace files yet.",
                "builtin-note",
            ))
            return lines

        if not long:
            names = [str(row.get("display") or row["path"]).strip() for row in rows]
            lines.append(output_line(" ".join(name for name in names if name), "builtin-help-row"))
            return lines

        width = max((len(str(item.get("display") or item["path"])) for item in rows), default=4)
        path_header = f"{'path':<{width}}"
        size_header = f"{'size':<8}"
        modified_header = "modified"
        lines.append(output_line(f"  {path_header}  {size_header}  {modified_header}", "builtin-table-header"))
        for row in rows:
            path = str(row.get("display") or row["path"])
            if row["kind"] == "directory":
                lines.append(output_line(f"  {path:<{width}}  folder", "builtin-table-row"))
                continue
            item = cast(dict[str, object], row["item"])
            size = format_bytes(_workspace_item_size(item))
            mtime = _format_clock(str(item.get("mtime") or ""))
            lines.append(output_line(f"  {path:<{width}}  {size:<8}  {mtime}", "builtin-table-row"))
        return lines

    if subcommand in {"show", "cat"}:
        if len(parts) != 3:
            return [output_line("Usage: file show <file>")]
        try:
            text = read_owner_workspace_text_file(owner, parts[2], cfg)
        except Exception as exc:
            return _workspace_command_error(exc)
        file_lines = text.splitlines() or [""]
        return [output_line(f"file: {parts[2]}", "builtin-section")] + text_lines(file_lines)

    if subcommand == "diff":
        return run_builtin_diff(parts, owner, cfg, tab_id=tab_id)

    if subcommand in {"add", "edit", "download"}:
        expected = (
            "file add [file]"
            if subcommand == "add"
            else f"file {subcommand} <file>"
        )
        if (
            (subcommand == "add" and len(parts) > 3)
            or (subcommand in {"edit", "download"} and len(parts) != 3)
        ):
            return [output_line(f"Usage: {expected}")]
        if subcommand in {"add", "edit"} and not _can_manage_workspace_files(owner, team_role):
            return _workspace_write_denied()
        if subcommand == "add":
            return [output_line("file add requires the browser Files panel — reload the page and try again.")]
        if len(parts) != 3:
            return [output_line(f"Usage: file {subcommand} <file>")]
        if subcommand == "download":
            return [output_line("file download requires the browser Files panel — reload the page and try again.")]
        return [output_line(
            f"file {subcommand} requires the browser Files panel — reload the page and try again."
        )]

    if subcommand in {"rm", "delete"}:
        if len(parts) != 3:
            return [output_line("Usage: file rm <file-or-folder>")]
        if not _can_manage_workspace_files(owner, team_role):
            return _workspace_write_denied()
        return [output_line("file rm requires browser confirmation — reload the page and try again.")]

    if subcommand in {"move", "mv"}:
        if len(parts) != 4:
            return [output_line("Usage: file move <source> <destination>")]
        if not _can_manage_workspace_files(owner, team_role):
            return _workspace_write_denied()
        try:
            if workspace_path_has_glob(parts[2]):
                matches = expand_owner_workspace_path_pattern(owner, parts[2], cfg)
                if not matches:
                    return [output_line(f"file: no matches: {parts[2]}")]
                destination_is_directory = parts[3] == "/" or any(
                    directory["path"] == parts[3].strip("/")
                    for directory in list_owner_workspace_directories(owner, cfg)
                )
                if len(matches) > 1 and not destination_is_directory:
                    return [output_line("file: destination must be an existing folder when moving multiple matches")]
                lines = []
                for match in matches:
                    moved = move_owner_workspace_path(owner, match.path, parts[3], cfg)
                    lines.append(output_line(f"file: moved {moved.source} to {moved.destination}", "builtin-success"))
                return lines
            moved = move_owner_workspace_path(owner, parts[2], parts[3], cfg)
        except Exception as exc:
            return _workspace_command_error(exc)
        return [output_line(f"file: moved {moved.source} to {moved.destination}", "builtin-success")]

    if subcommand in {"copy", "cp"}:
        if len(parts) != 4:
            return [output_line("Usage: file copy <source> <destination>")]
        if not _can_manage_workspace_files(owner, team_role):
            return _workspace_write_denied()
        try:
            copied = copy_owner_workspace_file(owner, parts[2], parts[3], cfg)
        except Exception as exc:
            return _workspace_command_error(exc)
        return [output_line(
            f"file: copied {copied.source} to {copied.destination}",
            "builtin-success",
        )]

    if subcommand == "touch":
        if len(parts) != 3:
            return [output_line("Usage: file touch <file>")]
        if not _can_manage_workspace_files(owner, team_role):
            return _workspace_write_denied()
        try:
            touched = touch_owner_workspace_file(owner, parts[2], cfg)
        except Exception as exc:
            return _workspace_command_error(exc)
        action = "created" if touched["created"] else "updated"
        return [output_line(f"file: {action} {touched['path']}", "builtin-success")]

    return [
        output_line(f"file: unknown subcommand '{subcommand}'"),
        output_line(
            "Usage: file [list | show <file> | diff <source1> <source2> | add <file> | edit <file> | "
            "download <file> | copy <source> <destination> | move <source> <destination> | "
            "touch <file> | rm <file-or-folder> | help]"
        ),
    ]


def run_builtin_workspace_alias(
    command: str,
    session_id: str,
    *,
    owner_context: OwnerContext | None = None,
    team_role: str = "",
    tab_id: str = "",
) -> list[dict[str, object]]:
    parts = split_command_argv(command)
    root = parts[0].lower() if parts else ""
    if root == "ls":
        return run_builtin_workspace(
            "file list " + " ".join(parts[1:]),
            session_id,
            owner_context=owner_context,
            team_role=team_role,
        )
    if root == "ll":
        return run_builtin_workspace(
            "file list -l " + " ".join(parts[1:]),
            session_id,
            owner_context=owner_context,
            team_role=team_role,
        )
    if root == "cat":
        if len(parts) != 2:
            return [output_line("Usage: cat <file>")]
        return run_builtin_workspace(f"file show {parts[1]}", session_id, owner_context=owner_context, team_role=team_role)
    if root == "diff":
        owner = _workspace_owner_context(session_id, owner_context)
        return run_builtin_diff(parts, owner, resolve_effective_cfg(), tab_id=tab_id)
    if root == "rm":
        if len(parts) != 2:
            return [output_line("Usage: rm <file-or-folder>")]
        return run_builtin_workspace(f"file rm {parts[1]}", session_id, owner_context=owner_context, team_role=team_role)
    if root == "mv":
        if len(parts) != 3:
            return [output_line("Usage: mv <source> <destination>")]
        return run_builtin_workspace(
            f"file move {parts[1]} {parts[2]}",
            session_id,
            owner_context=owner_context,
            team_role=team_role,
        )
    if root == "cp":
        if len(parts) != 3:
            return [output_line("Usage: cp <source> <destination>")]
        return run_builtin_workspace(
            f"file copy {parts[1]} {parts[2]}",
            session_id,
            owner_context=owner_context,
            team_role=team_role,
        )
    if root == "touch":
        if len(parts) != 2:
            return [output_line("Usage: touch <file>")]
        return run_builtin_workspace(
            f"file touch {parts[1]}",
            session_id,
            owner_context=owner_context,
            team_role=team_role,
        )
    if root == "mkdir" and not _can_manage_workspace_files(_workspace_owner_context(session_id, owner_context), team_role):
        return _workspace_write_denied()
    if root in {"cd", "grep", "head", "mkdir", "sort", "tail", "uniq", "wc"}:
        return [output_line(f"{root}: handled in the browser workspace terminal")]
    return [output_line(
        "Usage: file [list | show <file> | diff <source1> <source2> | add <file> | edit <file> | "
        "download <file> | copy <source> <destination> | move <source> <destination> | "
        "touch <file> | rm <file-or-folder> | help]"
    )]
