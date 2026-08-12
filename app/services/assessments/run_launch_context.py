# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared protected context for one app-owned Assessment run."""

from dataclasses import dataclass
from typing import Any

from services.runs.signal_context import RunOutputSignalContext


@dataclass(frozen=True)
class AssessmentRunLaunchContext:
    trusted_execution_args: tuple[str, ...]
    output_signal_context: RunOutputSignalContext | None = None
    reviewed_execution: object | None = None

    def broker_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "trusted_execution_args": self.trusted_execution_args,
        }
        if self.output_signal_context is not None:
            kwargs["output_signal_context"] = self.output_signal_context
        if self.reviewed_execution is not None:
            kwargs["reviewed_execution"] = self.reviewed_execution
        return kwargs


__all__ = ["AssessmentRunLaunchContext"]
