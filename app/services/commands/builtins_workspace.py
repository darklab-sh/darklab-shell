"""Session file built-in command handlers."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Sequence, cast

from config import CFG
from services.commands.builtins_format import (
    ansi_underline,
    format_bytes,
    format_native_record,
    output_line,
    text_lines,
)
from services.commands.registry import split_command_argv
from services.workspace.files import (
    InvalidWorkspacePath,
    WorkspaceBinaryFile,
    WorkspaceDisabled,
    WorkspaceFileNotFound,
    WorkspacePathNotFound,
    WorkspacePermissionDenied,
    WorkspaceQuotaExceeded,
    expand_workspace_path_pattern,
    list_workspace_directories,
    list_workspace_files,
    move_workspace_path,
    read_workspace_text_file,
    workspace_path_has_glob,
    workspace_settings,
    workspace_usage,
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
        return [output_line("file: session file storage is disabled on this instance")]
    if isinstance(exc, WorkspaceFileNotFound):
        return [output_line("file: file was not found")]
    if isinstance(exc, WorkspacePathNotFound):
        return [output_line("file: session file or folder was not found")]
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


def _underline_text(text: str) -> str:
    return ansi_underline(text)


def run_builtin_workspace(command: str, session_id: str) -> list[dict[str, object]]:
    parts = split_command_argv(command)
    subcommand = parts[1].lower() if len(parts) > 1 else "help"

    if subcommand in {"help", "--help", "-h"}:
        return [
            output_line("Session file commands:", "builtin-section"),
            output_line("  file list [-lR] [folder]", "builtin-help-row"),
            output_line("  file ls [-lR] [folder]", "builtin-help-row"),
            output_line("  file show <file>", "builtin-help-row"),
            output_line("  file add [file]", "builtin-help-row"),
            output_line("  file edit <file>", "builtin-help-row"),
            output_line("  file download <file>", "builtin-help-row"),
            output_line("  file move <source> <destination>", "builtin-help-row"),
            output_line("  file rm <file-or-folder>", "builtin-help-row"),
            output_line("", "builtin-spacer"),
            output_line("Aliases:", "builtin-section"),
            output_line("  ls [-lR]    -> file list [-lR]", "builtin-help-row"),
            output_line("  ll [-R]     -> file list -l [-R]", "builtin-help-row"),
            output_line("  cat <file>  -> file show <file>", "builtin-help-row"),
            output_line("  mv <source> <destination>  -> file move <source> <destination>", "builtin-help-row"),
            output_line("  rm <file-or-folder>   -> file rm <file-or-folder>", "builtin-help-row"),
            output_line("", "builtin-spacer"),
            output_line("Example flow:", "builtin-section"),
            output_line("  Create targets.txt from the Files panel.", "builtin-note"),
            output_line("  Run: nmap -iL targets.txt", "builtin-help-row"),
            output_line("  Run: curl -o response.html https://ip.darklab.sh", "builtin-help-row"),
        ]

    if subcommand in {"list", "ls"}:
        long, recursive, target, usage_error = _parse_workspace_list_command(parts)
        if usage_error:
            return [output_line(usage_error)]
        try:
            settings = workspace_settings(CFG)
            files = list_workspace_files(session_id, CFG)
            directories = list_workspace_directories(session_id, CFG)
            usage = workspace_usage(session_id, CFG)
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
                    expand_workspace_path_pattern(session_id, target, CFG),
                    files,
                )
            except Exception as exc:
                return _workspace_command_error(exc)
        else:
            rows = _workspace_list_rows(files, directories, recursive=recursive, target=target)
        if not rows:
            lines.append(output_line(
                "  No matching session files." if target else "  No session files yet.",
                "builtin-note",
            ))
            return lines

        if not long:
            names = [str(row.get("display") or row["path"]).strip() for row in rows]
            lines.append(output_line(" ".join(name for name in names if name), "builtin-help-row"))
            return lines

        width = max((len(str(item.get("display") or item["path"])) for item in rows), default=4)
        path_header = f"{_underline_text('path')}{' ' * max(0, width - len('path'))}"
        size_header = f"{_underline_text('size')}{' ' * (8 - len('size'))}"
        modified_header = _underline_text("modified")
        lines.append(output_line(f"  {path_header}  {size_header}  {modified_header}", "builtin-help-row"))
        for row in rows:
            path = str(row.get("display") or row["path"])
            if row["kind"] == "directory":
                lines.append(output_line(f"  {path:<{width}}  folder", "builtin-help-row"))
                continue
            item = cast(dict[str, object], row["item"])
            size = format_bytes(_workspace_item_size(item))
            mtime = _format_clock(str(item.get("mtime") or ""))
            lines.append(output_line(f"  {path:<{width}}  {size:<8}  {mtime}", "builtin-help-row"))
        return lines

    if subcommand in {"show", "cat"}:
        if len(parts) != 3:
            return [output_line("Usage: file show <file>")]
        try:
            text = read_workspace_text_file(session_id, parts[2])
        except Exception as exc:
            return _workspace_command_error(exc)
        file_lines = text.splitlines() or [""]
        return [output_line(f"file: {parts[2]}", "builtin-section")] + text_lines(file_lines)

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
        return [output_line("file rm requires browser confirmation — reload the page and try again.")]

    if subcommand in {"move", "mv"}:
        if len(parts) != 4:
            return [output_line("Usage: file move <source> <destination>")]
        try:
            if workspace_path_has_glob(parts[2]):
                matches = expand_workspace_path_pattern(session_id, parts[2], CFG)
                if not matches:
                    return [output_line(f"file: no matches: {parts[2]}")]
                destination_is_directory = parts[3] == "/" or any(
                    directory["path"] == parts[3].strip("/")
                    for directory in list_workspace_directories(session_id, CFG)
                )
                if len(matches) > 1 and not destination_is_directory:
                    return [output_line("file: destination must be an existing folder when moving multiple matches")]
                lines = []
                for match in matches:
                    moved = move_workspace_path(session_id, match.path, parts[3], CFG)
                    lines.append(output_line(f"file: moved {moved.source} to {moved.destination}", "builtin-success"))
                return lines
            moved = move_workspace_path(session_id, parts[2], parts[3], CFG)
        except Exception as exc:
            return _workspace_command_error(exc)
        return [output_line(f"file: moved {moved.source} to {moved.destination}", "builtin-success")]

    return [
        output_line(f"file: unknown subcommand '{subcommand}'"),
        output_line(
            "Usage: file [list | show <file> | add <file> | edit <file> | "
            "download <file> | move <source> <destination> | rm <file-or-folder> | help]"
        ),
    ]


def run_builtin_workspace_alias(command: str, session_id: str) -> list[dict[str, object]]:
    parts = split_command_argv(command)
    root = parts[0].lower() if parts else ""
    if root == "ls":
        return run_builtin_workspace("file list " + " ".join(parts[1:]), session_id)
    if root == "ll":
        return run_builtin_workspace("file list -l " + " ".join(parts[1:]), session_id)
    if root == "cat":
        if len(parts) != 2:
            return [output_line("Usage: cat <file>")]
        return run_builtin_workspace(f"file show {parts[1]}", session_id)
    if root == "rm":
        if len(parts) != 2:
            return [output_line("Usage: rm <file-or-folder>")]
        return run_builtin_workspace(f"file rm {parts[1]}", session_id)
    if root == "mv":
        if len(parts) != 3:
            return [output_line("Usage: mv <source> <destination>")]
        return run_builtin_workspace(f"file move {parts[1]} {parts[2]}", session_id)
    if root in {"cd", "grep", "head", "mkdir", "sort", "tail", "uniq", "wc"}:
        return [output_line(f"{root}: handled in the browser workspace terminal")]
    return [output_line(
        "Usage: file [list | show <file> | add <file> | edit <file> | "
        "download <file> | move <source> <destination> | rm <file-or-folder> | help]"
    )]
