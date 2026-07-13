"""Workflow execution service contracts."""

from __future__ import annotations


class WorkflowActiveExecutionLimitExceeded(ValueError):
    def __init__(self, limit: int):
        self.limit = int(limit)
        super().__init__(f"Active workflow execution limit reached ({self.limit}).")
