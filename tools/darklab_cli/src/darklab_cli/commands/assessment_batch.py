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


def handle_assessment_batch(client: DarklabClient, args: argparse.Namespace) -> int:
    match args.assessment_batch_command:
        case "plan":
            return handle_batch_plan(client, args)
        case "start":
            return handle_batch_start(client, args)
        case "list":
            return handle_batch_list(client, args)
        case "show":
            return handle_batch_show(client, args)
        case "follow":
            return handle_batch_follow(client, args)
        case "cancel":
            return handle_batch_cancel(client, args)
    return die("unknown assessment batch command")


__all__ = ["handle_assessment_batch"]
