# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Workspace output sinks layered over app-native run post-filters."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.commands.registry_workspace import normalize_workspace_command_path
from services.runs.output_sink_files import preflight_output_sink_destination, write_output_sink_text
from services.teams.capabilities import Capability, role_can
from services.teams.scope import OwnerContext
from services.workspace.files import (
    InvalidWorkspacePath,
    WorkspaceDisabled,
    workspace_settings,
)


class SyntheticPostFilterProcessor:
    """Apply app-native post-filter stages and an optional workspace output sink."""

    def __init__(self, spec):
        from services.runs.postfilters import SyntheticPostFilterStageProcessor  # noqa: PLC0415

        self.spec = spec or {}
        self.sink = self.spec.get("sink") if isinstance(self.spec, dict) else None
        self._sink_owner: OwnerContext | None = None
        self._sink_cfg: Mapping[str, Any] | None = None
        self._sink_lines: list[str] = []
        self._sink_bytes = 0
        self._sink_max_bytes = 0
        self.output_sink_error = ""
        self.output_sink_path = str((self.sink or {}).get("path") or "")
        stages = self.spec.get("stages") if isinstance(self.spec, dict) else None
        if stages is not None:
            self.stages = [SyntheticPostFilterStageProcessor(stage) for stage in stages]
        else:
            self.stages = [SyntheticPostFilterStageProcessor(self.spec)]

    @property
    def suppresses_terminal_output(self) -> bool:
        return bool(self.sink and self.sink.get("kind") in {"redirect", "append"})

    def should_publish_output_line(self, line: str) -> bool:
        """Publish only redirect failures while keeping redirected output hidden."""
        if not self.suppresses_terminal_output:
            return True
        return bool(self.output_sink_error and str(line).startswith("[error] output redirection failed:"))

    def configure_output_sink(
        self,
        *,
        owner_context: OwnerContext,
        team_role: str = "",
        workspace_cwd: str = "",
        cfg: Mapping[str, Any] | None = None,
    ) -> None:
        if not self.sink:
            return
        if owner_context.is_team and not role_can(team_role, Capability.MANAGE_WORKSPACE_FILES):
            raise ValueError("Your team role can view Files but can't change them.")
        try:
            settings = workspace_settings(cfg)
        except WorkspaceDisabled as exc:
            raise ValueError("Workspace file storage is disabled on this instance.") from exc
        try:
            self.output_sink_path = normalize_workspace_command_path(self.output_sink_path, workspace_cwd)
        except InvalidWorkspacePath as exc:
            raise ValueError(str(exc)) from exc
        preflight_output_sink_destination(owner_context, self.output_sink_path, cfg)
        self._sink_owner = owner_context
        self._sink_cfg = cfg
        self._sink_max_bytes = settings.max_file_bytes

    def _capture_sink_lines(self, lines: list[str]) -> None:
        if not self.sink or self.output_sink_error:
            return
        for line in lines:
            text = str(line)
            if not text.endswith("\n"):
                text += "\n"
            encoded_size = len(text.encode("utf-8"))
            if self._sink_max_bytes and self._sink_bytes + encoded_size > self._sink_max_bytes:
                self.output_sink_error = "output exceeds the workspace max file size"
                self._sink_lines = []
                self._sink_bytes = 0
                return
            self._sink_lines.append(text)
            self._sink_bytes += encoded_size

    def _finalize_output_sink(self) -> list[str]:
        if not self.sink:
            return []
        if not self._sink_owner:
            self.output_sink_error = "workspace output sink was not configured"
        if not self.output_sink_error:
            assert self._sink_owner is not None
            self.output_sink_error = write_output_sink_text(
                self._sink_owner,
                self.output_sink_path,
                "".join(self._sink_lines),
                self._sink_cfg,
                append=self.sink.get("kind") == "append",
            )
        if self.output_sink_error:
            return [f"[error] output redirection failed: {self.output_sink_error}\n"]
        return []

    def process_output_line(self, line: str) -> list[str]:
        lines = [line]
        for stage in self.stages:
            next_lines = []
            for current in lines:
                next_lines.extend(stage.process_output_line(current))
            lines = next_lines
        self._capture_sink_lines(lines)
        return lines

    def finalize_output_lines(self) -> list[str]:
        lines: list[str] = []
        for stage in self.stages:
            next_lines = []
            for current in lines:
                next_lines.extend(stage.process_output_line(current))
            next_lines.extend(stage.finalize_output_lines())
            lines = next_lines
        self._capture_sink_lines(lines)
        return [*lines, *self._finalize_output_sink()]
