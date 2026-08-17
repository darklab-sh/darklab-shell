# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Parser registration for durable assessment-batch commands."""

from __future__ import annotations

import argparse
from .assessment_batch_retry import register_assessment_batch_retry_parser


def _bounded_integer(label: str, minimum: int, maximum: int):
    def parse(value: str) -> int:
        try:
            parsed = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"{label} must be an integer") from exc
        if not minimum <= parsed <= maximum:
            raise argparse.ArgumentTypeError(
                f"{label} must be between {minimum} and {maximum}"
            )
        return parsed

    return parse


def _add_selection_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        metavar="ENTITY_ID",
        help="Include one confirmed assessment target; repeat to include more.",
    )
    parser.add_argument(
        "--exclude-target",
        action="append",
        default=[],
        metavar="ENTITY_ID",
        help="Exclude one assessment target; repeat to exclude more.",
    )
    parser.add_argument(
        "--category",
        action="append",
        default=[],
        help="Include one check category; repeat to include more.",
    )
    parser.add_argument(
        "--exclude-category",
        action="append",
        default=[],
        help="Exclude one check category; repeat to exclude more.",
    )
    parser.add_argument(
        "--include-standard",
        action="store_true",
        help="Include standard-policy checks in addition to safe checks.",
    )
    parser.add_argument(
        "--item-limit",
        type=_bounded_integer("item limit", 1, 512),
        default=128,
        help="Maximum selected commands; default 128, max 512.",
    )
    parser.add_argument(
        "--max-parallel",
        type=_bounded_integer("batch concurrency", 1, 8),
        default=8,
        help="Active commands in this batch; default 8, max 8.",
    )
    parser.add_argument(
        "--max-owner-parallel",
        type=_bounded_integer("owner concurrency", 1, 32),
        default=16,
        help="Active commands across this owner; default 16, max 32.",
    )
    parser.add_argument(
        "--max-instance-parallel",
        type=_bounded_integer("instance concurrency", 1, 64),
        default=32,
        help="Active commands across the instance; default 32, max 64.",
    )


def register_assessment_batch_parser(commands: argparse._SubParsersAction) -> None:
    batch = commands.add_parser(
        "batch", help="Preview, start, follow, and cancel bounded assessment batches."
    )
    actions = batch.add_subparsers(dest="assessment_batch_command", required=True)

    for name, help_text in (
        ("plan", "Compile and print a read-only assessment batch preview."),
        ("start", "Compile a fresh preview and optionally start the confirmed batch."),
    ):
        command = actions.add_parser(name, help=help_text)
        command.add_argument("project_id", metavar="PROJECT", help="Active Project slug or id.")
        command.add_argument("assessment_id", metavar="ASSESSMENT_ID")
        _add_selection_options(command)
        if name == "start":
            command.add_argument(
                "--confirm",
                action="store_true",
                help="Start the freshly previewed batch; otherwise remain read-only.",
            )
            command.add_argument(
                "--confirm-standard",
                action="store_true",
                help="Separately acknowledge selected standard-policy commands.",
            )
        command.add_argument("--format", choices=("text", "json"), default="text")

    listing = actions.add_parser("list", help="List durable batches for one Project.")
    listing.add_argument("project_id", metavar="PROJECT", help="Active Project slug or id.")
    listing.add_argument("--assessment-id")
    listing.add_argument("--cursor")
    listing.add_argument(
        "--limit", type=_bounded_integer("page size", 1, 100), default=50
    )
    listing.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    show = actions.add_parser("show", help="Show one batch and optional bounded item or event pages.")
    show.add_argument("batch_id", metavar="BATCH_ID")
    show.add_argument("--items", action="store_true", help="Include one item page.")
    show.add_argument("--events", action="store_true", help="Include one event page.")
    show.add_argument("--item-cursor", type=_bounded_integer("item cursor", 0, 512), default=0)
    show.add_argument("--event-cursor", type=_bounded_integer("event cursor", 0, 2**63 - 1), default=0)
    show.add_argument("--limit", type=_bounded_integer("page size", 1, 100), default=100)
    show.add_argument("--format", choices=("text", "json"), default="text")

    follow = actions.add_parser("follow", help="Follow batch events from a resumable sequence cursor.")
    follow.add_argument("batch_id", metavar="BATCH_ID")
    follow.add_argument("--cursor", type=_bounded_integer("event cursor", 0, 2**63 - 1), default=0)
    follow.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="Seconds between empty polls; default 1.0.",
    )
    follow.add_argument("--format", choices=("text", "ndjson"), default="text")

    cancel = actions.add_parser("cancel", help="Preview or request cancellation of one batch.")
    cancel.add_argument("batch_id", metavar="BATCH_ID")
    cancel.add_argument(
        "--confirm", action="store_true", help="Request cancellation; otherwise remain read-only."
    )
    cancel.add_argument("--format", choices=("text", "json"), default="text")
    register_assessment_batch_retry_parser(actions, _add_selection_options)
__all__ = ["register_assessment_batch_parser"]
