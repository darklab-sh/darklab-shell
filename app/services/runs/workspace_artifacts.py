"""Helpers for run-scoped workspace artifact capture."""

from __future__ import annotations

import config as app_config
from services.commands.registry import AMASS_DEFAULT_WORKSPACE_DIR, CommandValidationResult
from services.teams.scope import OwnerContext, personal_owner_context
from services.workspace.files import InvalidWorkspacePath, WorkspaceDisabled, resolve_owner_workspace_path

APP_MANAGED_WORKSPACE_ARTIFACT_PREFIXES = (
    AMASS_DEFAULT_WORKSPACE_DIR.strip("/"),
)


def _artifact_owner_context(session_id: str, owner_context: OwnerContext | None = None) -> OwnerContext:
    return owner_context or personal_owner_context(session_id)


def workspace_artifact_size(
    session_id: str,
    workspace_path: str,
    *,
    owner_context: OwnerContext | None = None,
) -> int:
    try:
        path = resolve_owner_workspace_path(
            _artifact_owner_context(session_id, owner_context),
            workspace_path,
            app_config.CFG,
        )
        if path.is_file():
            return max(0, int(path.stat().st_size))
    except (InvalidWorkspacePath, OSError, WorkspaceDisabled):
        return 0
    return 0


def workspace_artifacts_from_validation(
    validation: CommandValidationResult,
    session_id: str,
) -> list[dict]:
    reads = list(dict.fromkeys(validation.workspace_reads))
    writes = list(dict.fromkeys(validation.workspace_writes))
    read_set = set(reads)
    write_set = set(writes)
    ordered_paths = reads + [path for path in writes if path not in read_set]
    artifacts = []
    for workspace_path in ordered_paths:
        if is_app_managed_workspace_artifact_path(workspace_path):
            continue
        if workspace_path in read_set and workspace_path in write_set:
            kind = "read_write"
        elif workspace_path in write_set:
            kind = "output"
        else:
            kind = "input"
        artifacts.append({
            "workspace_path": workspace_path,
            "display_name": workspace_path.rsplit("/", 1)[-1],
            "kind": kind,
            "detected_by": "workspace_flag",
        })
    return artifacts


def is_app_managed_workspace_artifact_path(workspace_path: str) -> bool:
    normalized = str(workspace_path or "").strip().replace("\\", "/").strip("/")
    if not normalized:
        return False
    return any(
        normalized == prefix or normalized.startswith(f"{prefix}/")
        for prefix in APP_MANAGED_WORKSPACE_ARTIFACT_PREFIXES
        if prefix
    )


def workspace_artifacts_with_sizes(
    session_id: str,
    artifacts: object,
    *,
    owner_context: OwnerContext | None = None,
) -> list[dict]:
    sized = []
    artifact_items = artifacts if isinstance(artifacts, list) else []
    for item in artifact_items:
        if not isinstance(item, dict):
            continue
        artifact = dict(item)
        workspace_path = str(artifact.get("workspace_path") or "")
        artifact["byte_size"] = workspace_artifact_size(session_id, workspace_path, owner_context=owner_context)
        sized.append(artifact)
    return sized
