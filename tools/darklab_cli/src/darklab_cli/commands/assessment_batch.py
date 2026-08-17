# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Dispatch durable assessment-batch CLI commands."""

from __future__ import annotations

import argparse

from ..client import DarklabClient, die
from .assessment_batch_preview import handle_batch_plan, handle_batch_start
from .assessment_batch_reads import (
    handle_batch_cancel,
    handle_batch_follow,
    handle_batch_list,
    handle_batch_show,
)
from .assessment_batch_retry import handle_batch_retry


def handle_assessment_batch(client: DarklabClient, args: argparse.Namespace) -> int:
    handlers = {
        "plan": handle_batch_plan,
        "start": handle_batch_start,
        "list": handle_batch_list,
        "show": handle_batch_show,
        "follow": handle_batch_follow,
        "cancel": handle_batch_cancel,
        "retry": handle_batch_retry,
    }
    handler = handlers.get(args.assessment_batch_command)
    return handler(client, args) if handler else die("unknown assessment batch command")


__all__ = ["handle_assessment_batch"]
