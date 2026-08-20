# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Parser registration for immutable assessment-batch retries."""

from __future__ import annotations

import argparse
from collections.abc import Callable


def register_assessment_batch_retry_parser(
    actions: argparse._SubParsersAction,
    add_selection_options: Callable[[argparse.ArgumentParser], None],
) -> None:
    retry = actions.add_parser(
        "retry", help="Preview or start a new batch for failed or unfinished work."
    )
    retry.add_argument("batch_id", metavar="BATCH_ID")
    add_selection_options(retry)
    retry.add_argument(
        "--confirm",
        action="store_true",
        help="Start the retry; otherwise remain read-only.",
    )
    retry.add_argument(
        "--confirm-standard",
        action="store_true",
        help="Separately acknowledge selected standard-policy commands.",
    )
    retry.add_argument("--format", choices=("text", "json"), default="text")


__all__ = ["register_assessment_batch_retry_parser"]
