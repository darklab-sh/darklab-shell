# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Surface-neutral child-run launch inputs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from services.runs.signal_context import RunOutputSignalContext


@dataclass(frozen=True)
class ChildLaunchSpec:
    """Complete private and public inputs for one already-claimed child run."""

    execution_command: str
    display_command: str
    private_values: tuple[str, ...] = ()
    trusted_execution_args: tuple[str, ...] = ()
    reviewed_execution: object | None = None
    output_signal_context: RunOutputSignalContext | None = None
    run_finalized_hook: Callable[[str, dict[str, Any]], None] | None = None
    run_cleanup_hook: Callable[[], None] | None = None
    suppress_run_complete_notification: bool = False

    def __post_init__(self) -> None:
        if not self.execution_command.strip():
            raise ValueError("child execution command is required")
        if not self.display_command.strip():
            raise ValueError("child display command is required")
        if any(not isinstance(value, str) for value in self.private_values):
            raise ValueError("child private values must be strings")
        if any(not isinstance(value, str) for value in self.trusted_execution_args):
            raise ValueError("child trusted execution arguments must be strings")

    def broker_kwargs(self) -> dict[str, object]:
        """Return optional trusted inputs without serializing or logging them."""
        values: dict[str, object] = {
            "private_values": self.private_values,
            "trusted_execution_args": self.trusted_execution_args,
        }
        if self.reviewed_execution is not None:
            values["reviewed_execution"] = self.reviewed_execution
        if self.output_signal_context is not None:
            values["output_signal_context"] = self.output_signal_context
        if self.run_finalized_hook is not None:
            values["run_finalized_hook"] = self.run_finalized_hook
        if self.run_cleanup_hook is not None:
            values["run_cleanup_hook"] = self.run_cleanup_hook
        if self.suppress_run_complete_notification:
            values["suppress_run_complete_notification"] = True
        return values


__all__ = ["ChildLaunchSpec"]
