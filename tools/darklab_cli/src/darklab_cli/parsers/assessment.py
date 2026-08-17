# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Parser registration for assessment-cycle commands."""

from __future__ import annotations

import argparse


_STATUS_CHOICES = ("active", "completed", "archived")
_CHECK_STATE_CHOICES = (
    "not_started", "running", "covered", "needs_review", "failed", "blocked",
    "skipped", "not_applicable",
)
_MANUAL_STATE_CHOICES = ("blocked", "skipped", "not_applicable")
_POLICY_LEVEL_CHOICES = ("safe", "standard", "intrusive", "destructive")
_EVIDENCE_STATE_CHOICES = ("available", "unavailable", "none")


def register_assessment_parser(subparsers: argparse._SubParsersAction) -> None:
    assessment = subparsers.add_parser("assessment", help="Review and update project assessment cycles.")
    commands = assessment.add_subparsers(dest="assessment_command", required=True)

    listing = commands.add_parser("list", help="List assessment cycles for one project.")
    listing.add_argument("project_id", metavar="PROJECT", help="Active Project slug or id.")
    listing.add_argument("--status", choices=_STATUS_CHOICES)
    listing.add_argument("--include-archived", action="store_true")
    listing.add_argument("--limit", type=int, default=50, help="Rows to return; default 50, max 200.")
    listing.add_argument("--offset", type=int, default=0)
    listing.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    show = commands.add_parser("show", help="Show one assessment cycle and its coverage rollup.")
    show.add_argument("project_id", metavar="PROJECT", help="Active Project slug or id.")
    show.add_argument("assessment_id")
    show.add_argument("--format", choices=("text", "json"), default="text")

    checks = commands.add_parser("checks", help="List checks for one assessment cycle.")
    checks.add_argument("project_id", metavar="PROJECT", help="Active Project slug or id.")
    checks.add_argument("assessment_id")
    checks.add_argument("--category")
    checks.add_argument("--state", choices=_CHECK_STATE_CHOICES)
    checks.add_argument("--target-type")
    checks.add_argument("--policy-level", choices=_POLICY_LEVEL_CHOICES)
    checks.add_argument("--evidence-state", choices=_EVIDENCE_STATE_CHOICES)
    checks.add_argument("--limit", type=int, default=50, help="Rows to return; default 50, max 200.")
    checks.add_argument("--offset", type=int, default=0)
    checks.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    set_state = commands.add_parser("set-state", help="Set a reasoned manual state for one assessment check.")
    set_state.add_argument("project_id", metavar="PROJECT", help="Active Project slug or id.")
    set_state.add_argument("assessment_id")
    set_state.add_argument("check_id")
    set_state.add_argument("state", choices=_MANUAL_STATE_CHOICES)
    set_state.add_argument("--reason", required=True)
    set_state.add_argument("--format", choices=("text", "json"), default="text")

    clear_state = commands.add_parser(
        "clear-state", help="Clear a manual check state and restore its evidence-derived state."
    )
    clear_state.add_argument("project_id", metavar="PROJECT", help="Active Project slug or id.")
    clear_state.add_argument("assessment_id")
    clear_state.add_argument("check_id")
    clear_state.add_argument("--format", choices=("text", "json"), default="text")

    start_action = commands.add_parser(
        "start-action", help="Preview or explicitly start an Assessment check recommendation."
    )
    start_action.add_argument("project_id", metavar="PROJECT", help="Active Project slug or id.")
    start_action.add_argument("assessment_id")
    start_action.add_argument("check_id")
    start_action.add_argument("--http-profile-id")
    start_action.add_argument("--source-run-id")
    start_action.add_argument("--parameter-observation-id")
    start_action.add_argument("--schema-artifact-id")
    start_action.add_argument(
        "--confirm", action="store_true",
        help="Start the previewed action; without this flag the command is read-only.",
    )
    start_action.add_argument("--workspace-cwd")
    start_action.add_argument("--format", choices=("text", "json"), default="text")


__all__ = ["register_assessment_parser"]
