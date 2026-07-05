"""Workspace exception and payload models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class WorkspaceError(ValueError):
    """Base class for workspace validation and operation errors."""


class WorkspaceDisabled(WorkspaceError):
    """Raised when workspace operations are requested while disabled."""


class InvalidWorkspacePath(WorkspaceError):
    """Raised when a user-facing workspace path is unsafe or unsupported."""


class WorkspaceQuotaExceeded(WorkspaceError):
    """Raised when a write would exceed configured workspace limits."""


class WorkspaceFileNotFound(WorkspaceError):
    """Raised when a validated workspace path does not point at a file."""


class WorkspacePathNotFound(WorkspaceError):
    """Raised when a validated workspace path does not exist."""


class WorkspaceBinaryFile(WorkspaceError):
    """Raised when a workspace file is not safe to display as text."""


class WorkspacePermissionDenied(WorkspaceError):
    """Raised when workspace permissions prevent an app-mediated operation."""


@dataclass(frozen=True)
class WorkspaceSettings:
    enabled: bool
    backend: str
    root: Path
    quota_bytes: int
    max_file_bytes: int
    max_files: int
    inactivity_ttl_hours: int


@dataclass(frozen=True)
class WorkspaceUsage:
    bytes_used: int
    file_count: int


@dataclass(frozen=True)
class WorkspaceDeleteResult:
    path: str
    kind: str
    file_count: int


@dataclass(frozen=True)
class WorkspaceMoveResult:
    source: str
    destination: str
    kind: str
    file_count: int


@dataclass(frozen=True)
class WorkspacePathMatch:
    path: str
    kind: str
    file_count: int


@dataclass(frozen=True)
class WorkspaceMigrationResult:
    migrated_files: int = 0
    skipped_files: int = 0
    migrated_directories: int = 0
    skipped_directories: int = 0
    migrated_file_paths: tuple[str, ...] = ()
    skipped_file_paths: tuple[str, ...] = ()
