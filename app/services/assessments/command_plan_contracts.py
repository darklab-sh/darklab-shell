# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Value contracts shared by bounded Assessment command plans."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandPlan:
    command: str
    boundary: str
    request_limit: int | None
    time_limit_seconds: int | None
    credential_use: str = "none"
