# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Command line entry point for the darklab_shell API client."""

from __future__ import annotations

import argparse
from datetime import datetime
import getpass
import json
import os
from pathlib import Path
import shlex
import sys
from typing import Any, NoReturn
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .client import DarklabClient, DarklabCliError, die, iter_sse_events, load_config, print_json, save_config_value
from .commands import handle_advisory, handle_assessment, handle_evidence, handle_finding, handle_probe, handle_risk
from .formatting import (
    print_collection as _print_collection,
    print_payload as _print_payload,
    print_table as _print_table,
)
from .parsers import (register_advisory_parser, register_assessment_parser,
                      register_evidence_parser, register_finding_parser, register_probe_parser, register_risk_parser)

STREAM_INCOMPLETE_EXIT_CODE = 2
STREAM_INTERRUPTED_EXIT_CODE = 130
COMPLETION_SHELLS = ("bash", "zsh", "fish")
COMPLETION_INSTALL_SHELLS = ("auto", *COMPLETION_SHELLS)
NOTIFICATION_CHANNEL_KIND_CHOICES = ("webhook", "slack", "discord", "telegram", "pushover", "email")
TEAM_ROLE_CHOICES = ("owner", "admin", "operator", "viewer")
WATCHER_POLICY_SIGNAL_CLASS_CHOICES = ("findings", "entities", "ports")
HISTORY_TYPE_CHOICES = ("all", "runs", "runs_external", "runs_builtin", "external", "builtin")
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="darklab",
        description=(
            "Headless darklab_shell client for runs, history, projects, probes, assessments, advisories, "
            "Atlas, schedules, watchers, and notifications."
        ),
    )
    parser.add_argument("--api-url", help="darklab_shell base URL")
    parser.add_argument("--token", help="tok_ session token")
    parser.add_argument("--team", help="Team id for this request; DARKLAB_TEAM also works.")
    parser.add_argument("--timeout", type=float, default=None, help="HTTP timeout in seconds")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    completion = sub.add_parser("completion", help="Print or install shell completion for bash, zsh, or fish.")
    completion.add_argument("completion_action", choices=(*COMPLETION_SHELLS, "install"), metavar="SHELL|install")
    completion.add_argument(
        "--shell",
        choices=COMPLETION_INSTALL_SHELLS,
        default="auto",
        help="Shell to install for; default auto.",
    )
    whoami = sub.add_parser("whoami", help="Show token metadata and last-auth timestamp.")
    whoami.add_argument("--format", choices=("text", "json"), default="text")
    team = sub.add_parser("team", help="Create, join, inspect, and manage teams.")
    team_sub = team.add_subparsers(dest="team_command", required=True)

    team_status = team_sub.add_parser("status", help="Show the active CLI team scope.")
    team_status.add_argument("--format", choices=("text", "json"), default="text")

    team_list = team_sub.add_parser("list", help="List teams for the current token.")
    team_list.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    team_create = team_sub.add_parser("create", help="Create a team and print its one-time recovery code.")
    team_create.add_argument("name")
    team_create.add_argument("--slug")
    team_create.add_argument("--display-name")
    team_create.add_argument("--format", choices=("text", "json"), default="text")

    team_switch = team_sub.add_parser("switch", help="Persist the default CLI team scope.")
    team_switch.add_argument("team_ref", metavar="team-id|name|personal")
    team_switch.add_argument("--format", choices=("text", "json"), default="text")

    team_info = team_sub.add_parser("info", help="Show one team with members and invites.")
    team_info.add_argument("team_id")
    team_info.add_argument("--format", choices=("text", "json"), default="text")

    team_members = team_sub.add_parser("members", help="List members for one team.")
    team_members.add_argument("team_id")
    team_members.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    team_invite = team_sub.add_parser("invite", help="Create or revoke team invites.")
    team_invite_sub = team_invite.add_subparsers(dest="team_invite_command", required=True)
    team_invite_create = team_invite_sub.add_parser("create", help="Create a team invite.")
    team_invite_create.add_argument("team_id")
    team_invite_create.add_argument("--role", choices=TEAM_ROLE_CHOICES, default="operator")
    team_invite_create.add_argument("--label")
    team_invite_create.add_argument("--expires-at")
    team_invite_create.add_argument("--max-uses", type=int, default=1)
    team_invite_create.add_argument("--format", choices=("text", "json"), default="text")
    team_invite_revoke = team_invite_sub.add_parser("revoke", help="Revoke a team invite.")
    team_invite_revoke.add_argument("team_id")
    team_invite_revoke.add_argument("invite_id")
    team_invite_revoke.add_argument("--format", choices=("text", "json"), default="text")

    team_join = team_sub.add_parser("join", help="Redeem a team invite code.")
    team_join.add_argument("code")
    team_join.add_argument("--display-name")
    team_join.add_argument("--format", choices=("text", "json"), default="text")

    team_member = team_sub.add_parser("member", help="Update or remove team members.")
    team_member_sub = team_member.add_subparsers(dest="team_member_command", required=True)
    team_member_update = team_member_sub.add_parser("update", help="Update a team member role or display name.")
    team_member_update.add_argument("team_id")
    team_member_update.add_argument("member_id")
    team_member_update.add_argument("--role", choices=TEAM_ROLE_CHOICES)
    team_member_update.add_argument("--display-name")
    team_member_update.add_argument("--format", choices=("text", "json"), default="text")
    team_member_remove = team_member_sub.add_parser("remove", help="Remove a team member.")
    team_member_remove.add_argument("team_id")
    team_member_remove.add_argument("member_id")
    team_member_remove.add_argument("--format", choices=("text", "json"), default="text")

    team_leave = team_sub.add_parser("leave", help="Leave a team.")
    team_leave.add_argument("team_id")
    team_leave.add_argument("--format", choices=("text", "json"), default="text")

    team_recovery = team_sub.add_parser("recovery", help="Rotate or redeem team recovery codes.")
    team_recovery_sub = team_recovery.add_subparsers(dest="team_recovery_command", required=True)
    team_recovery_rotate = team_recovery_sub.add_parser("rotate", help="Rotate a team recovery code.")
    team_recovery_rotate.add_argument("team_id")
    team_recovery_rotate.add_argument("--format", choices=("text", "json"), default="text")
    team_recovery_redeem = team_recovery_sub.add_parser("redeem", help="Redeem a recovery code as an owner.")
    team_recovery_redeem.add_argument("code")
    team_recovery_redeem.add_argument("--display-name")
    team_recovery_redeem.add_argument("--format", choices=("text", "json"), default="text")

    run = sub.add_parser("run", help="Start a non-interactive command run.")
    run.add_argument("run_command")
    run.add_argument("--project", dest="project_id")
    run.add_argument("--link-project", dest="link_project", help="Project name to resolve before starting the run.")
    run.add_argument("--wait", action="store_true", help="Wait for the run to finish instead of streaming output.")
    run.add_argument(
        "--wait-timeout",
        type=float,
        default=None,
        help="Server-side wait timeout in seconds; default 30, max 3600.",
    )
    run.add_argument("--format", choices=("text", "json", "ndjson"), default="text")
    run_follow = run.add_mutually_exclusive_group()
    run_follow.add_argument("--follow", dest="follow", action="store_true", default=True)
    run_follow.add_argument("--no-follow", dest="follow", action="store_false")

    active = sub.add_parser("active", help="List active runs for the current token.")
    active.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    tail = sub.add_parser("tail", help="Follow an active run stream.")
    tail.add_argument("run_id")
    tail.add_argument("--format", choices=("text", "ndjson"), default="text")
    tail.add_argument("--after", default="")

    cancel = sub.add_parser("cancel", help="Cancel an active current-token run.")
    cancel.add_argument("run_id")
    cancel.add_argument("--format", choices=("text", "json"), default="text")

    history = sub.add_parser("history", help="List completed run history.")
    history.add_argument("--project", dest="project_id")
    history.add_argument(
        "--type",
        dest="history_type",
        choices=HISTORY_TYPE_CHOICES,
        default="all",
        help="Filter run type: all, runs, runs_external/external, or runs_builtin/builtin.",
    )
    history.add_argument("--since")
    history.add_argument("--until")
    history.add_argument("--limit", type=int, default=50, help="Rows to return; default 50, max 100.")
    history.add_argument("--offset", type=int, default=0)
    history.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    grep = sub.add_parser("grep", help="Search saved output across completed runs.")
    grep.add_argument("pattern")
    grep.add_argument("--context", type=int, default=2, help="Output lines before and after each match; default 2, max 10.")
    grep.add_argument("--project", dest="project_id")
    grep.add_argument("--since")
    grep.add_argument("--until")
    grep.add_argument("--limit", type=int, default=50, help="Matches to return; default 50, max 100.")
    grep.add_argument("--offset", type=int, default=0)
    grep.add_argument("--signal", action="append", default=[], help="Only return lines with this structured signal.")
    grep.add_argument("--kind", action="append", default=[], help="Only return lines with this severity kind.")
    grep.add_argument("--not-kind", action="append", default=[], help="Exclude lines with this severity kind.")
    grep.add_argument("--role", action="append", default=[], help="Only return lines with this structural role.")
    grep.add_argument("--entity", action="append", default=[], help="Only return lines with this entity value.")
    grep.add_argument("--entity-type", action="append", default=[], help="Only return lines with this entity type.")
    grep.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    show = sub.add_parser("show", help="Show one completed run summary.")
    show.add_argument("run_id")
    show.add_argument("--lines", type=int, default=0)
    show.add_argument("--format", choices=("text", "json"), default="text")

    output = sub.add_parser("output", help="Print stored run output.")
    output.add_argument("run_id")
    output.add_argument("--range", dest="line_range", help="1-based line range to fetch, such as 10-40.")
    output.add_argument("--signal", action="append", default=[], help="Only return lines with this structured signal.")
    output.add_argument("--kind", action="append", default=[], help="Only return lines with this severity kind.")
    output.add_argument("--not-kind", action="append", default=[], help="Exclude lines with this severity kind.")
    output.add_argument("--role", action="append", default=[], help="Only return lines with this structural role.")
    output.add_argument("--entity", action="append", default=[], help="Only return lines with this entity value.")
    output.add_argument("--entity-type", action="append", default=[], help="Only return lines with this entity type.")
    output.add_argument("--format", choices=("text", "json"), default="text")

    artifacts = sub.add_parser("artifacts", help="List artifacts for one completed run.")
    artifacts.add_argument("run_id")

    projects = sub.add_parser("projects", help="List projects.")
    projects.add_argument("--format", choices=("text", "json", "ndjson"), default="text")
    projects.add_argument("--limit", type=int, default=50, help="Rows to return; default 50, max 100.")
    projects.add_argument("--offset", type=int, default=0)

    project = sub.add_parser("project", help="Show one project.")
    project.add_argument("project_id")
    project.add_argument("--format", choices=("text", "json"), default="text")

    project_link = sub.add_parser("project-link", help="Link a completed run to a project.")
    project_link.add_argument("run_id")
    project_link.add_argument("project_id")
    project_link.add_argument("--format", choices=("text", "json"), default="text")

    project_unlink = sub.add_parser("project-unlink", help="Remove a completed run from a project.")
    project_unlink.add_argument("run_id")
    project_unlink.add_argument("project_id")
    project_unlink.add_argument("--format", choices=("text", "json"), default="text")

    project_findings = sub.add_parser("project-findings", help="List project findings.")
    project_findings.add_argument("project_id")
    project_findings.add_argument("--limit", type=int, default=50, help="Rows to return; default 50, max 100.")
    project_findings.add_argument("--offset", type=int, default=0)
    project_findings.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    project_runs = sub.add_parser("project-runs", help="List runs linked to a project.")
    project_runs.add_argument("project_id")
    project_runs.add_argument("--limit", type=int, default=50, help="Rows to return; default 50, max 100.")
    project_runs.add_argument("--offset", type=int, default=0)
    project_runs.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    project_entities = sub.add_parser("project-entities", help="List Atlas entities linked to a project.")
    project_entities.add_argument("project_id")
    project_entities.add_argument("--entity-type")
    project_entities.add_argument("--limit", type=int, default=50, help="Rows to return; default 50, max 100.")
    project_entities.add_argument("--offset", type=int, default=0)
    project_entities.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    project_packages = sub.add_parser("project-packages", help="List project evidence packages.")
    project_packages.add_argument("project_id")
    project_packages.add_argument("--limit", type=int, default=50, help="Rows to return; default 50, max 100.")
    project_packages.add_argument("--offset", type=int, default=0)
    project_packages.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    for register_parser in (register_advisory_parser, register_assessment_parser,
                            register_evidence_parser, register_finding_parser, register_probe_parser, register_risk_parser):
        register_parser(sub)

    atlas = sub.add_parser("atlas", help="Read Atlas summaries, source runs, entities, and findings.")
    atlas_sub = atlas.add_subparsers(dest="atlas_command", required=True)

    atlas_summary = atlas_sub.add_parser("summary", help="Show Atlas counts.")
    _add_atlas_common_filters(atlas_summary, include_entity_type=False)
    atlas_summary.add_argument("--format", choices=("text", "json"), default="text")

    atlas_runs = atlas_sub.add_parser("runs", help="List runs that contribute Atlas data.")
    atlas_runs.add_argument("--q")
    atlas_runs.add_argument("--run-id")
    atlas_runs.add_argument("--limit", type=int, default=30, help="Rows to return; default 30, max 50.")
    atlas_runs.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    atlas_entities = atlas_sub.add_parser("entities", help="List Atlas entities.")
    _add_atlas_common_filters(atlas_entities)
    atlas_entities.add_argument("--limit", type=int, default=50, help="Rows to return; default 50, max 200.")
    atlas_entities.add_argument("--offset", type=int, default=0)
    atlas_entities.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    atlas_entity = atlas_sub.add_parser("entity", help="Show one Atlas entity.")
    atlas_entity.add_argument("entity_id")
    atlas_entity.add_argument("--format", choices=("text", "json"), default="text")

    atlas_findings = atlas_sub.add_parser("findings", help="List Atlas findings.")
    _add_atlas_common_filters(atlas_findings, include_entity_type=False)
    atlas_findings.add_argument("--review-state", action="append", default=[])
    atlas_findings.add_argument("--limit", type=int, default=50, help="Rows to return; default 50, max 200.")
    atlas_findings.add_argument("--offset", type=int, default=0)
    atlas_findings.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    atlas_finding = atlas_sub.add_parser("finding", help="Show one Atlas finding.")
    atlas_finding.add_argument("finding_id")
    atlas_finding.add_argument("--format", choices=("text", "json"), default="text")

    download = sub.add_parser(
        "download",
        help="Download one artifact by id.",
        description="Download one run artifact. Use `darklab artifacts <run_id>` first to list artifact ids.",
    )
    download.add_argument("run_id")
    download.add_argument(
        "--artifact",
        required=True,
        help="Artifact id from `darklab artifacts <run_id>`.",
    )
    download.add_argument("--out", default=".", help="Destination directory.")

    schedule = sub.add_parser("schedule", help="Manage recurring scheduled commands.")
    schedule_sub = schedule.add_subparsers(dest="schedule_command", required=True)

    schedule_list = schedule_sub.add_parser("list", help="List scheduled commands.")
    schedule_list.add_argument("--limit", type=int, default=50, help="Rows to return; default 50, max 100.")
    schedule_list.add_argument("--offset", type=int, default=0)
    schedule_list.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    schedule_create = schedule_sub.add_parser("create", help="Create a scheduled command.")
    schedule_cadence = schedule_create.add_mutually_exclusive_group(required=True)
    schedule_cadence.add_argument("--cron")
    schedule_cadence.add_argument("--every", metavar="PRESET", help="Cadence preset: hourly, daily, or weekly.")
    schedule_create.add_argument("--label")
    schedule_create.add_argument("--timezone")
    schedule_create.add_argument("--format", choices=("text", "json"), default="text")
    schedule_create.add_argument("schedule_argv", nargs=argparse.REMAINDER, metavar="-- COMMAND")

    schedule_info = schedule_sub.add_parser("info", help="Show one scheduled command.")
    schedule_info.add_argument("schedule_id")
    schedule_info.add_argument("--format", choices=("text", "json"), default="text")

    schedule_pause = schedule_sub.add_parser("pause", help="Pause a scheduled command.")
    schedule_pause.add_argument("schedule_id")
    schedule_pause.add_argument("--format", choices=("text", "json"), default="text")

    schedule_resume = schedule_sub.add_parser("resume", help="Resume a scheduled command.")
    schedule_resume.add_argument("schedule_id")
    schedule_resume.add_argument("--format", choices=("text", "json"), default="text")

    schedule_delete = schedule_sub.add_parser("delete", help="Delete a scheduled command.")
    schedule_delete.add_argument("schedule_id")
    schedule_delete.add_argument("--format", choices=("text", "json"), default="text")

    schedule_run = schedule_sub.add_parser("run", help="Fire a scheduled command immediately.")
    schedule_run.add_argument("schedule_id")
    schedule_run.add_argument("--format", choices=("text", "json"), default="text")

    schedule_fires = schedule_sub.add_parser("fires", help="List fire audit rows for a scheduled command.")
    schedule_fires.add_argument("schedule_id")
    schedule_fires.add_argument("--limit", type=int, default=50, help="Rows to return; default 50, max 100.")
    schedule_fires.add_argument("--offset", type=int, default=0)
    schedule_fires.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    watch = sub.add_parser("watch", help="Manage recurring change-detection watchers.")
    watch_sub = watch.add_subparsers(dest="watch_command", required=True)

    watch_list = watch_sub.add_parser("list", help="List change-detection watchers.")
    watch_list.add_argument("--limit", type=int, default=50, help="Rows to return; default 50, max 100.")
    watch_list.add_argument("--offset", type=int, default=0)
    watch_list.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    watch_create = watch_sub.add_parser(
        "create",
        help="Create a watcher from a baseline run or from its first run.",
        usage=(
            "darklab watch create [--first-run] (--cron CRON | --every PRESET) "
            "[--label LABEL] [--project PROJECT_ID] [--timezone TIMEZONE] [--disabled] "
            "[--suppress-removals] [--notify-metadata-changes] "
            "[--ignore-line-pattern PATTERN] [--alert-after-repeated-changes N] "
            "[--alert-signal-class {findings,entities,ports}] [--format {text,json}] "
            "[baseline_run_id] [-- COMMAND]"
        ),
        description=(
            "Create a watcher from a completed baseline run, or use --first-run to capture "
            "the first successful watcher run as the baseline. Add `-- COMMAND` to override "
            "the baseline command or provide the first-run command."
        ),
        epilog=(
            "Examples: darklab watch create run_123 --every hourly; "
            "darklab watch create run_123 --every daily -- curl -I https://darklab.sh; "
            "darklab watch create --first-run --every hourly -- nmap -sV darklab.sh"
        ),
    )
    watch_create.add_argument(
        "--first-run",
        action="store_true",
        help="Capture the first successful watcher run as the baseline.",
    )
    watch_create.add_argument("--cron")
    watch_create.add_argument("--every", metavar="PRESET", help="Cadence preset: hourly, daily, or weekly.")
    watch_create.add_argument("--label")
    watch_create.add_argument("--project", dest="project_id", help="Project id to show this watcher in Project Monitoring.")
    watch_create.add_argument("--timezone")
    watch_create.add_argument("--disabled", action="store_true", help="Create the watcher paused.")
    watch_create.add_argument("--suppress-removals", action="store_true", help="Ignore removal-only diffs.")
    watch_create.add_argument("--notify-metadata-changes", action="store_true", help="Treat metadata-only changes as diffs.")
    watch_create.add_argument(
        "--ignore-line-pattern",
        action="append",
        default=[],
        help="Textual fallback line pattern to ignore; repeat for multiple patterns.",
    )
    watch_create.add_argument(
        "--alert-after-repeated-changes",
        type=int,
        default=1,
        metavar="N",
        help="Send changed notifications only after N repeated changes; 1-10, default 1.",
    )
    watch_create.add_argument(
        "--alert-signal-class",
        choices=WATCHER_POLICY_SIGNAL_CLASS_CHOICES,
        action="append",
        default=[],
        help="Signal class allowed to send changed notifications; repeat for multiple classes.",
    )
    watch_create.add_argument("--format", choices=("text", "json"), default="text")
    watch_create.add_argument("watch_argv", nargs=argparse.REMAINDER, metavar="[baseline_run_id] [-- COMMAND]")

    watch_info = watch_sub.add_parser("info", help="Show one watcher.")
    watch_info.add_argument("watcher_id")
    watch_info.add_argument("--format", choices=("text", "json"), default="text")

    watch_pause = watch_sub.add_parser("pause", help="Pause a watcher and its owned schedule.")
    watch_pause.add_argument("watcher_id")
    watch_pause.add_argument("--format", choices=("text", "json"), default="text")

    watch_resume = watch_sub.add_parser("resume", help="Resume a paused watcher.")
    watch_resume.add_argument("watcher_id")
    watch_resume.add_argument("--format", choices=("text", "json"), default="text")

    watch_delete = watch_sub.add_parser("delete", help="Delete a watcher and its owned schedule.")
    watch_delete.add_argument("watcher_id")
    watch_delete.add_argument("--format", choices=("text", "json"), default="text")

    watch_run = watch_sub.add_parser("run", help="Fire a watcher immediately.")
    watch_run.add_argument("watcher_id")
    watch_run.add_argument("--format", choices=("text", "json"), default="text")

    watch_accept = watch_sub.add_parser("accept", help="Accept the latest watcher fire as the new baseline.")
    watch_accept.add_argument("watcher_id")
    watch_accept.add_argument("--run-id", help="Specific completed watcher run to accept instead of the latest fire.")
    watch_accept.add_argument("--format", choices=("text", "json"), default="text")

    watch_set_project = watch_sub.add_parser("set-project", help="Assign or clear a watcher's Project Monitoring link.")
    watch_set_project.add_argument("watcher_id")
    watch_set_project.add_argument("project_id", nargs="?", help="Project id to assign.")
    watch_set_project.add_argument("--clear", action="store_true", help="Clear the watcher project link.")
    watch_set_project.add_argument("--format", choices=("text", "json"), default="text")

    watch_set_policy = watch_sub.add_parser("set-policy", help="Update watcher noise and notification policy.")
    watch_set_policy.add_argument("watcher_id")
    watch_set_policy.add_argument(
        "--ignore-line-pattern",
        action="append",
        default=[],
        help="Replace ignored textual fallback patterns; repeat for multiple patterns.",
    )
    watch_set_policy.add_argument(
        "--clear-ignore-line-patterns",
        action="store_true",
        help="Clear ignored textual fallback patterns.",
    )
    watch_set_policy.add_argument(
        "--alert-after-repeated-changes",
        type=int,
        metavar="N",
        help="Send changed notifications only after N repeated changes; 1-10.",
    )
    watch_set_policy.add_argument(
        "--alert-signal-class",
        choices=WATCHER_POLICY_SIGNAL_CLASS_CHOICES,
        action="append",
        default=[],
        help="Replace signal classes allowed to send changed notifications; repeat for multiple classes.",
    )
    watch_set_policy.add_argument(
        "--clear-alert-signal-classes",
        action="store_true",
        help="Allow all signal classes to send changed notifications.",
    )
    watch_set_policy.add_argument("--format", choices=("text", "json"), default="text")

    watch_fires = watch_sub.add_parser("fires", help="List watcher fire audit rows.")
    watch_fires.add_argument("watcher_id")
    watch_fires.add_argument("--limit", type=int, default=50, help="Rows to return; default 50, max 100.")
    watch_fires.add_argument("--offset", type=int, default=0)
    watch_fires.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    notify = sub.add_parser("notify", help="Manage outbound notification channels and delivery events.")
    notify_sub = notify.add_subparsers(dest="notify_command", required=True)

    notify_list = notify_sub.add_parser("list", help="List notification channels.")
    notify_list.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    notify_create = notify_sub.add_parser("create", help="Create a notification channel.")
    notify_create.add_argument("kind", metavar="kind")
    notify_create.add_argument("--label")
    notify_create.add_argument("--trigger", action="append", default=[])
    notify_create.add_argument("--config", action="append", default=[], help="Channel config as KEY=VALUE.")
    notify_create.add_argument("--secret-file", help="JSON file containing write-only secret fields.")
    notify_create.add_argument("--format", choices=("text", "json"), default="text")

    notify_update = notify_sub.add_parser("update", help="Update a notification channel.")
    notify_update.add_argument("channel_id")
    notify_update.add_argument("--label")
    notify_update.add_argument("--trigger", action="append", default=[])
    notify_update.add_argument("--config", action="append", default=[], help="Channel config as KEY=VALUE.")
    notify_update.add_argument("--format", choices=("text", "json"), default="text")

    notify_mute = notify_sub.add_parser("mute", help="Mute a notification channel.")
    notify_mute.add_argument("channel_id")
    notify_mute.add_argument("--format", choices=("text", "json"), default="text")

    notify_unmute = notify_sub.add_parser("unmute", help="Unmute a notification channel.")
    notify_unmute.add_argument("channel_id")
    notify_unmute.add_argument("--format", choices=("text", "json"), default="text")

    notify_delete = notify_sub.add_parser("delete", help="Delete a notification channel.")
    notify_delete.add_argument("channel_id")
    notify_delete.add_argument("--format", choices=("text", "json"), default="text")

    notify_test = notify_sub.add_parser("test", help="Send a test notification.")
    notify_test.add_argument("channel_id")
    notify_test.add_argument("--format", choices=("text", "json"), default="text")

    notify_events = notify_sub.add_parser("events", help="List notification delivery audit rows.")
    notify_events.add_argument("--status")
    notify_events.add_argument("--channel", dest="channel_id")
    notify_events.add_argument("--trigger")
    notify_events.add_argument("--limit", type=int, default=50, help="Rows to return; default 50, max 100.")
    notify_events.add_argument("--offset", type=int, default=0)
    notify_events.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    return parser


def _add_atlas_common_filters(parser: argparse.ArgumentParser, *, include_entity_type: bool = True) -> None:
    parser.add_argument("--q")
    parser.add_argument("--project", dest="project_id")
    parser.add_argument("--run-id")
    parser.add_argument("--orphan-filter", choices=("hide", "all", "only"), default="hide")
    parser.add_argument("--suppression-filter", choices=("hide", "all", "only"), default="hide")
    if include_entity_type:
        parser.add_argument("--entity-type", choices=("domain", "ip", "url", "hash", "cve"))


def _completion_subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _completion_parser_paths(
    parser: argparse.ArgumentParser,
    path: tuple[str, ...] = (),
) -> dict[tuple[str, ...], argparse.ArgumentParser]:
    paths = {path: parser}
    for name, child in _completion_subparsers(parser).items():
        paths.update(_completion_parser_paths(child, (*path, name)))
    return paths


def _completion_option_data(parser: argparse.ArgumentParser) -> tuple[list[str], dict[str, list[str]]]:
    options: list[str] = []
    choices: dict[str, list[str]] = {}
    for action in parser._actions:
        option_strings = [str(option) for option in action.option_strings if option]
        if not option_strings:
            continue
        options.extend(option_strings)
        action_choices = getattr(action, "choices", None)
        if action_choices:
            values = [str(value) for value in action_choices]
            for option in option_strings:
                choices[option] = values
    return sorted(set(options)), choices


def _completion_static_argument_choices(path: tuple[str, ...]) -> list[str]:
    if path == ("completion",):
        return [*COMPLETION_SHELLS, "install"]
    if path == ("notify", "create"):
        return list(NOTIFICATION_CHANNEL_KIND_CHOICES)
    if path == ("team", "invite", "create"):
        return list(TEAM_ROLE_CHOICES)
    return []


def _completion_spec() -> dict[str, Any]:
    parser = _parser()
    paths = _completion_parser_paths(parser)
    spec: dict[str, Any] = {}
    for path, path_parser in paths.items():
        options, option_choices = _completion_option_data(path_parser)
        spec[":".join(path)] = {
            "arguments": _completion_static_argument_choices(path),
            "choices": option_choices,
            "options": options,
            "subcommands": sorted(_completion_subparsers(path_parser)),
        }
    return spec


def _completion_words(values: list[str] | tuple[str, ...]) -> str:
    return " ".join(str(value) for value in values)


def _completion_shell_words(values: list[str] | tuple[str, ...]) -> str:
    return " ".join(shlex.quote(str(value)) for value in values)


def _completion_path_cases(spec: dict[str, Any], field: str) -> str:
    lines: list[str] = []
    for key in sorted(spec):
        words = _completion_shell_words(spec[key].get(field) or [])
        if not words:
            continue
        lines.append(f"    {shlex.quote(key)}) _darklab_comp_words {shlex.quote(words)} ;;")
    return "\n".join(lines)


def _completion_choice_cases(spec: dict[str, Any]) -> str:
    lines: list[str] = []
    for key in sorted(spec):
        for option, choices in sorted((spec[key].get("choices") or {}).items()):
            words = _completion_shell_words(choices)
            if not words:
                continue
            lines.append(f"    {shlex.quote(f'{key}:{option}')}) _darklab_comp_words {shlex.quote(words)}; return ;;")
    return "\n".join(lines)


def _completion_path_step_cases(spec: dict[str, Any]) -> str:
    lines: list[str] = []
    for key in sorted(spec):
        subcommands = _completion_shell_words(spec[key].get("subcommands") or [])
        if subcommands:
            lines.append(
                f"      {shlex.quote(key)}) "
                f"_darklab_word_in \"$word\" {shlex.quote(subcommands)} "
                "&& path_key=\"${path_key:+$path_key:}$word\" ;;"
            )
    return "\n".join(lines)


def _completion_bash(spec: dict[str, Any]) -> str:
    top_commands = _completion_shell_words(spec[""].get("subcommands") or [])
    return f"""# bash completion for darklab
_darklab_completion() {{
  local cur prev word path_key
  COMPREPLY=()
  cur="${{COMP_WORDS[COMP_CWORD]}}"
  prev="${{COMP_WORDS[COMP_CWORD-1]}}"

  _darklab_word_in() {{ case " $2 " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }}
  _darklab_comp_words() {{ COMPREPLY=( $(compgen -W "$1" -- "$cur") ); }}

  path_key=""
  for ((i=1; i<COMP_CWORD; i++)); do
    word="${{COMP_WORDS[i]}}"
    [[ "$word" == -* ]] && continue
    case "$path_key" in
{_completion_path_step_cases(spec)}
    esac
  done

  case "$path_key:$prev" in
{_completion_choice_cases(spec)}
  esac

  if [[ "$cur" == -* ]]; then
    case "$path_key" in
{_completion_path_cases(spec, "options")}
    esac
    return
  fi

  if [[ -z "$path_key" ]]; then
    _darklab_comp_words {shlex.quote(top_commands)}
    return
  fi
  case "$path_key" in
{_completion_path_cases(spec, "subcommands")}
  esac
  case "$path_key" in
{_completion_path_cases(spec, "arguments")}
  esac
}}
complete -F _darklab_completion darklab"""


def _completion_zsh(spec: dict[str, Any]) -> str:
    top_commands = _completion_shell_words(spec[""].get("subcommands") or [])
    return f"""#compdef darklab
_darklab() {{
  local cur prev word path_key
  cur="${{words[CURRENT]}}"
  prev="${{words[CURRENT-1]}}"

  _darklab_word_in() {{ case " $2 " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }}
  _darklab_comp_words() {{ compadd -- ${{(z)1}}; }}

  path_key=""
  for ((i=2; i<CURRENT; i++)); do
    word="${{words[i]}}"
    [[ "$word" == -* ]] && continue
    case "$path_key" in
{_completion_path_step_cases(spec)}
    esac
  done

  case "$path_key:$prev" in
{_completion_choice_cases(spec)}
  esac

  if [[ "$cur" == -* ]]; then
    case "$path_key" in
{_completion_path_cases(spec, "options")}
    esac
    return
  fi

  if [[ -z "$path_key" ]]; then
    _darklab_comp_words {shlex.quote(top_commands)}
    return
  fi
  case "$path_key" in
{_completion_path_cases(spec, "subcommands")}
  esac
  case "$path_key" in
{_completion_path_cases(spec, "arguments")}
  esac
}}
compdef _darklab darklab"""


def _fish_option(option: str) -> str:
    if option.startswith("--"):
        return f"-l {shlex.quote(option[2:])}"
    if option.startswith("-") and len(option) == 2:
        return f"-s {shlex.quote(option[1:])}"
    return f"-o {shlex.quote(option.lstrip('-'))}"


def _fish_condition(path: tuple[str, ...], spec: dict[str, Any]) -> str:
    if not path:
        return "__fish_use_subcommand"
    clauses = [f"__fish_seen_subcommand_from {shlex.quote(part)}" for part in path]
    if len(path) == 1:
        subcommands = spec[":".join(path)].get("subcommands") or []
        if subcommands:
            clauses.append("not __fish_seen_subcommand_from " + _completion_shell_words(subcommands))
    return "; and ".join(clauses)


def _completion_fish(spec: dict[str, Any]) -> str:
    lines = [
        "# fish completion for darklab",
        "complete -c darklab -f",
        f"complete -c darklab -f -n '__fish_use_subcommand' -a '{_completion_words(spec[''].get('subcommands') or [])}'",
    ]
    for key in sorted(spec):
        path = tuple(part for part in key.split(":") if part)
        condition = _fish_condition(path, spec)
        subcommands = spec[key].get("subcommands") or []
        if path and subcommands:
            lines.append(
                "complete -c darklab -f "
                f"-n {shlex.quote(condition)} -a {shlex.quote(_completion_words(subcommands))}"
            )
        arguments = spec[key].get("arguments") or []
        if arguments:
            lines.append(
                "complete -c darklab -f "
                f"-n {shlex.quote(condition)} -a {shlex.quote(_completion_words(arguments))}"
            )
        choices_by_option = spec[key].get("choices") or {}
        for option in spec[key].get("options") or []:
            choice_words = _completion_words(choices_by_option.get(option) or [])
            choice_arg = f" -xa {shlex.quote(choice_words)}" if choice_words else ""
            lines.append(
                "complete -c darklab -f "
                f"-n {shlex.quote(condition)} {_fish_option(option)}{choice_arg}"
            )
    return "\n".join(lines)


def _completion_script(shell: str) -> str:
    spec = _completion_spec()
    match shell:
        case "bash":
            return _completion_bash(spec)
        case "zsh":
            return _completion_zsh(spec)
        case "fish":
            return _completion_fish(spec)
    raise DarklabCliError(f"unsupported completion shell: {shell}")


def _detect_completion_shell() -> str:
    shell = Path(os.environ.get("SHELL", "")).name
    if shell in COMPLETION_SHELLS:
        return shell
    raise DarklabCliError("could not detect shell; pass --shell bash, --shell zsh, or --shell fish")


def _completion_install_path(shell: str) -> Path:
    if shell == "bash":
        data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
        return data_home / "bash-completion" / "completions" / "darklab"
    if shell == "zsh":
        return Path.home() / ".zfunc" / "_darklab"
    if shell == "fish":
        config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        return config_home / "fish" / "completions" / "darklab.fish"
    raise DarklabCliError(f"unsupported completion shell: {shell}")


def _install_completion(shell: str) -> str:
    resolved_shell = _detect_completion_shell() if shell == "auto" else shell
    path = _completion_install_path(resolved_shell)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_completion_script(resolved_shell) + "\n", encoding="utf-8")
    message = f"Installed {resolved_shell} completion to {path}"
    if resolved_shell == "zsh":
        message += (
            "\nIf completion is not already enabled, add this to your zsh startup file:\n"
            "  fpath=(~/.zfunc $fpath)\n"
            "  autoload -Uz compinit && compinit"
        )
    return message


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    raw_argv = sys.argv[1:] if argv is None else argv
    args = parser.parse_args(raw_argv)
    try:
        if args.command == "completion":
            if args.completion_action == "install":
                print(_install_completion(args.shell))
            else:
                print(_completion_script(args.completion_action))
            return 0
        client = DarklabClient(load_config(args))
        return _dispatch(client, args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return STREAM_INTERRUPTED_EXIT_CODE
    except DarklabCliError as exc:
        return die(str(exc))


def _dispatch(client: DarklabClient, args: argparse.Namespace) -> int:
    match args.command:
        case "whoami":
            return _print_payload(client.request("GET", "/whoami"), args.format)
        case "team":
            return _team(client, args)
        case "run":
            return _run(client, args)
        case "active":
            return _active(client, args)
        case "tail":
            return _tail(client, args.run_id, args.format, after=args.after)
        case "cancel":
            return _print_payload(client.request("POST", f"/runs/{args.run_id}/cancel"), args.format)
        case "history":
            payload = client.request("GET", "/history", params=_history_params(args))
            return _print_collection(
                payload,
                "runs",
                args.format,
                fields=("finished", "id", "status", "exit_code", "command"),
                reverse=True,
            )
        case "grep":
            params = {**_page_params(args), **_structured_selector_params(args), "q": args.pattern, "context": args.context}
            payload = client.request("GET", "/history/search", params=params)
            return _print_search_matches(payload, args.format)
        case "show":
            payload = client.request("GET", f"/history/{args.run_id}")
            if args.format == "json":
                return _print_payload(payload, "json")
            run = payload.get("run", {})
            print(f"{run.get('id')}  {run.get('status')}  {run.get('command')}")
            if args.lines:
                output = client.request("GET", f"/history/{args.run_id}/output", params={"format": "json"})
                for line in output.get("lines", [])[-args.lines:]:
                    print(line)
            return 0
        case "output":
            params = {
                **_structured_selector_params(args),
                "format": args.format,
                "range": args.line_range,
            }
            if args.format == "json":
                return _print_payload(client.request("GET", f"/runs/{args.run_id}/output", params=params), "json")
            text = client.request("GET", f"/runs/{args.run_id}/output", params=params)
            print(text, end="" if str(text).endswith("\n") else "\n")
            return 0
        case "artifacts":
            payload = client.request("GET", f"/history/{args.run_id}/artifacts")
            return _print_collection(payload, "artifacts", "text", fields=("id", "byte_size", "display_name"))
        case "projects":
            payload = client.request("GET", "/projects", params=_page_params(args))
            return _print_collection(payload, "projects", args.format, fields=("id", "status", "name"))
        case "project":
            payload = client.request("GET", f"/projects/{args.project_id}")
            return _print_payload(payload, args.format)
        case "project-link":
            payload = client.request("POST", f"/runs/{args.run_id}/projects/{args.project_id}")
            return _print_payload(payload, args.format)
        case "project-unlink":
            payload = client.request("DELETE", f"/runs/{args.run_id}/projects/{args.project_id}")
            return _print_payload(payload, args.format)
        case "project-findings":
            payload = client.request("GET", f"/projects/{args.project_id}/findings", params=_page_window_params(args))
            return _print_collection(payload, "findings", args.format, fields=("id", "status", "severity", "title"))
        case "project-runs":
            payload = client.request("GET", f"/projects/{args.project_id}/runs", params=_page_window_params(args))
            return _print_collection(payload, "runs", args.format, fields=("started", "id", "exit_code", "command"))
        case "project-entities":
            params = {**_page_window_params(args), "entity_type": args.entity_type}
            payload = client.request("GET", f"/projects/{args.project_id}/entities", params=params)
            return _print_collection(payload, "entities", args.format, fields=("type", "id", "value"))
        case "project-packages":
            payload = client.request("GET", f"/projects/{args.project_id}/packages", params=_page_window_params(args))
            return _print_collection(payload, "packages", args.format, fields=("id", "status", "name"))
        case "advisory" | "assessment" | "evidence" | "finding" | "probe" | "risk":
            handlers = {"advisory": handle_advisory, "assessment": handle_assessment,
                        "evidence": handle_evidence, "finding": handle_finding, "probe": handle_probe, "risk": handle_risk}
            return handlers[args.command](client, args)
        case "atlas":
            return _atlas(client, args)
        case "schedule":
            return _schedule(client, args)
        case "watch":
            return _watch(client, args)
        case "notify":
            return _notify(client, args)
        case "download":
            target = client.download(
                f"/history/{args.run_id}/artifacts/{args.artifact}",
                args.out,
            )
            print(target)
            return 0
    return die("unknown command")


def _team(client: DarklabClient, args: argparse.Namespace) -> int:
    match args.team_command:
        case "status":
            payload = {
                "team": client.config.team,
                "scope": "team" if client.config.team else "personal",
            }
            if args.format == "json":
                return _print_payload(payload, "json")
            print(f"scope: {payload['scope']}")
            print(f"team: {payload['team'] or '(none)'}")
            return 0
        case "list":
            payload = client.request("GET", "/teams")
            teams = payload.get("teams") if isinstance(payload, dict) else []
            if isinstance(teams, list):
                payload = {
                    **payload,
                    "teams": [
                        {**team, "role": _team_role(team)}
                        for team in teams
                        if isinstance(team, dict)
                    ],
                }
            return _print_collection(payload, "teams", args.format, fields=("id", "status", "role", "name"))
        case "create":
            payload = client.request("POST", "/teams", body={
                "name": args.name,
                "slug": args.slug,
                "display_name": args.display_name,
            })
            return _print_team_created(payload, args.format)
        case "switch":
            team_id = _resolve_team_ref(client, args.team_ref)
            save_config_value("team", team_id)
            payload = {"scope": "team" if team_id else "personal", "team": team_id}
            if args.format == "json":
                return _print_payload(payload, "json")
            print(f"scope: {payload['scope']}")
            if team_id:
                print(f"team: {team_id}")
            return 0
        case "info":
            return _print_team_detail(client.request("GET", f"/teams/{args.team_id}"), args.format)
        case "members":
            payload = client.request("GET", f"/teams/{args.team_id}")
            members = {"members": payload.get("members", [])}
            return _print_collection(members, "members", args.format, fields=("id", "role", "status", "display_name"))
        case "invite":
            return _team_invite(client, args)
        case "join":
            payload = client.request("POST", "/teams/join", body={
                "code": args.code,
                "display_name": args.display_name,
            })
            return _print_team_detail(payload, args.format)
        case "member":
            return _team_member(client, args)
        case "leave":
            return _print_payload(client.request("POST", f"/teams/{args.team_id}/leave"), args.format)
        case "recovery":
            return _team_recovery(client, args)
    return die("unknown team command")


def _team_invite(client: DarklabClient, args: argparse.Namespace) -> int:
    match args.team_invite_command:
        case "create":
            payload = client.request("POST", f"/teams/{args.team_id}/invites", body={
                "role": args.role,
                "label": args.label,
                "expires_at": args.expires_at,
                "max_uses": args.max_uses,
            })
            if args.format == "json":
                return _print_payload(payload, "json")
            invite = payload.get("invite") if isinstance(payload, dict) else {}
            if isinstance(invite, dict):
                print(f"invite: {invite.get('id')}")
                print(f"role: {invite.get('role')}")
                print(f"code: {invite.get('code')}")
            return 0
        case "revoke":
            return _print_payload(
                client.request("DELETE", f"/teams/{args.team_id}/invites/{args.invite_id}"),
                args.format,
            )
    return die("unknown team invite command")


def _team_member(client: DarklabClient, args: argparse.Namespace) -> int:
    match args.team_member_command:
        case "update":
            body: dict[str, Any] = {}
            if args.role is not None:
                body["role"] = args.role
            if args.display_name is not None:
                body["display_name"] = args.display_name
            if not body:
                raise DarklabCliError("team member update needs --role or --display-name.")
            payload = client.request("PATCH", f"/teams/{args.team_id}/members/{args.member_id}", body=body)
            return _print_team_member(payload, args.format)
        case "remove":
            return _print_payload(
                client.request("DELETE", f"/teams/{args.team_id}/members/{args.member_id}"),
                args.format,
            )
    return die("unknown team member command")


def _team_recovery(client: DarklabClient, args: argparse.Namespace) -> int:
    match args.team_recovery_command:
        case "rotate":
            payload = client.request("POST", f"/teams/{args.team_id}/recovery/rotate")
            if args.format == "json":
                return _print_payload(payload, "json")
            print(f"recovery code: {payload.get('recovery_code')}")
            print("Store this somewhere safe. It will not be shown again.")
            return 0
        case "redeem":
            payload = client.request("POST", "/teams/recovery/redeem", body={
                "code": args.code,
                "display_name": args.display_name,
            })
            return _print_team_detail(payload, args.format)
    return die("unknown team recovery command")


def _resolve_team_ref(client: DarklabClient, team_ref: str) -> str:
    ref = str(team_ref or "").strip()
    if ref.lower() in {"", "personal", "none", "-"}:
        return ""
    payload = client.request("GET", "/teams")
    teams = payload.get("teams") if isinstance(payload, dict) else []
    if not isinstance(teams, list):
        raise DarklabCliError("could not load teams for this token.")
    for team in teams:
        if not isinstance(team, dict):
            continue
        values = {str(team.get("id") or ""), str(team.get("slug") or ""), str(team.get("name") or "")}
        if ref in values:
            return str(team.get("id") or ref)
    raise DarklabCliError(f"team not found: {ref}")


def _team_role(team: dict[str, Any]) -> str:
    member = team.get("member")
    if isinstance(member, dict):
        return str(member.get("role") or "")
    return str(team.get("role") or "")


def _print_team_created(payload: dict[str, Any], output_format: str) -> int:
    if output_format == "json":
        return _print_payload(payload, "json")
    team = payload.get("team") if isinstance(payload, dict) else {}
    if isinstance(team, dict):
        _print_table([{**team, "role": _team_role(team)}], ("id", "status", "role", "name"))
    recovery_code = payload.get("recovery_code") if isinstance(payload, dict) else ""
    if recovery_code:
        print(f"recovery code: {recovery_code}")
        print("Store this somewhere safe. It will not be shown again.")
    return 0


def _print_team_detail(payload: dict[str, Any], output_format: str) -> int:
    if output_format == "json":
        return _print_payload(payload, "json")
    team = payload.get("team") if isinstance(payload, dict) else {}
    if isinstance(team, dict):
        _print_detail_section("Team", (
            ("ID", team.get("id")),
            ("Name", team.get("name")),
            ("Slug", team.get("slug")),
            ("Status", team.get("status")),
            ("Role", _team_role(team)),
        ))
    members = payload.get("members") if isinstance(payload, dict) else []
    if isinstance(members, list):
        _print_collection({"members": members}, "members", "text", fields=("id", "role", "status", "display_name"))
    return 0


def _print_team_member(payload: dict[str, Any], output_format: str) -> int:
    if output_format == "json":
        return _print_payload(payload, "json")
    member = payload.get("member") if isinstance(payload, dict) else {}
    if isinstance(member, dict):
        _print_table([member], ("id", "role", "status", "display_name"))
    return 0


def _schedule(client: DarklabClient, args: argparse.Namespace) -> int:
    match args.schedule_command:
        case "list":
            payload = client.request("GET", "/schedules", params=_page_window_params(args))
            return _print_collection(
                payload,
                "schedules",
                args.format,
                fields=("id", "enabled", "next_run_at", "label", "command_text"),
            )
        case "create":
            body = {
                "command": _schedule_command_text(args.schedule_argv),
                "cron_expr": args.cron,
                "cadence_preset": args.every,
                "label": args.label,
                "timezone": args.timezone,
            }
            return _print_schedule(client.request("POST", "/schedules", body=body), args.format)
        case "info":
            schedule_payload = client.request("GET", f"/schedules/{args.schedule_id}")
            fires_payload = client.request("GET", f"/schedules/{args.schedule_id}/fires", params={"limit": 5, "offset": 0})
            return _print_schedule_info(schedule_payload, fires_payload, args.format)
        case "pause":
            payload = client.request(
                "PATCH",
                f"/schedules/{args.schedule_id}",
                body={"enabled": False, "paused_reason": "paused"},
            )
            return _print_schedule(payload, args.format)
        case "resume":
            payload = client.request(
                "PATCH",
                f"/schedules/{args.schedule_id}",
                body={"enabled": True, "paused_reason": "", "last_error": "", "consecutive_failures": 0},
            )
            return _print_schedule(payload, args.format)
        case "delete":
            return _print_payload(client.request("DELETE", f"/schedules/{args.schedule_id}"), args.format)
        case "run":
            return _print_schedule_fire(client.request("POST", f"/schedules/{args.schedule_id}/run-now"), args.format)
        case "fires":
            payload = client.request("GET", f"/schedules/{args.schedule_id}/fires", params=_page_window_params(args))
            return _print_collection(
                payload,
                "fires",
                args.format,
                fields=("fired_at", "status", "run_id", "reason"),
            )
    return die("unknown schedule command")


def _schedule_command_text(argv: list[str]) -> str:
    parts = list(argv or [])
    if not parts or parts[0] != "--":
        raise DarklabCliError("schedule create needs -- before the command.")
    parts = parts[1:]
    command = shlex.join(parts).strip()
    if not command:
        raise DarklabCliError("schedule create needs a command after --.")
    return command


def _optional_command_text(argv: list[str], command_name: str) -> str:
    parts = list(argv or [])
    if not parts:
        return ""
    if parts[0] != "--":
        raise DarklabCliError(f"{command_name} needs -- before the command override.")
    command = shlex.join(parts[1:]).strip()
    if not command:
        raise DarklabCliError(f"{command_name} needs a command after --.")
    return command


class _DispatchArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise DarklabCliError(message)


def _watch_create_argv(args: argparse.Namespace) -> list[str]:
    parts: list[str] = []
    if args.first_run:
        parts.append("--first-run")
    if args.cron:
        parts.extend(["--cron", str(args.cron)])
    if args.every:
        parts.extend(["--every", str(args.every)])
    if args.label:
        parts.extend(["--label", str(args.label)])
    if getattr(args, "project_id", None):
        parts.extend(["--project", str(args.project_id)])
    if args.timezone:
        parts.extend(["--timezone", str(args.timezone)])
    if args.disabled:
        parts.append("--disabled")
    if args.suppress_removals:
        parts.append("--suppress-removals")
    if args.notify_metadata_changes:
        parts.append("--notify-metadata-changes")
    for pattern in getattr(args, "ignore_line_pattern", []) or []:
        parts.extend(["--ignore-line-pattern", str(pattern)])
    if getattr(args, "alert_after_repeated_changes", 1) != 1:
        parts.extend(["--alert-after-repeated-changes", str(args.alert_after_repeated_changes)])
    for signal_class in getattr(args, "alert_signal_class", []) or []:
        parts.extend(["--alert-signal-class", str(signal_class)])
    if args.format != "text":
        parts.extend(["--format", str(args.format)])
    parts.extend(list(args.watch_argv or []))
    return parts


def _watch_create_args(argv: list[str]) -> argparse.Namespace:
    parts = list(argv or [])
    command = ""
    if "--" in parts:
        separator_index = parts.index("--")
        command = _optional_command_text(parts[separator_index:], "watch create")
        parts = parts[:separator_index]

    parser = _DispatchArgumentParser(
        prog="darklab watch create",
        add_help=False,
    )
    parser.add_argument("--first-run", action="store_true")
    cadence = parser.add_mutually_exclusive_group(required=True)
    cadence.add_argument("--cron")
    cadence.add_argument("--every", metavar="PRESET")
    parser.add_argument("--label")
    parser.add_argument("--project", dest="project_id")
    parser.add_argument("--timezone")
    parser.add_argument("--disabled", action="store_true")
    parser.add_argument("--suppress-removals", action="store_true")
    parser.add_argument("--notify-metadata-changes", action="store_true")
    parser.add_argument("--ignore-line-pattern", action="append", default=[])
    parser.add_argument("--alert-after-repeated-changes", type=int, default=1)
    parser.add_argument("--alert-signal-class", choices=WATCHER_POLICY_SIGNAL_CLASS_CHOICES, action="append", default=[])
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("baseline_run_id", nargs="?")

    parsed = parser.parse_args(parts)
    parsed.command_override = command
    return parsed


def _print_schedule(payload: dict[str, Any], output_format: str) -> int:
    if output_format == "json":
        return _print_payload(payload, "json")
    schedule = payload.get("schedule") if isinstance(payload, dict) else {}
    if isinstance(schedule, dict):
        _print_table([schedule], ("id", "enabled", "next_run_at", "label", "command_text"))
    return 0


def _print_schedule_info(payload: dict[str, Any], fires_payload: dict[str, Any], output_format: str) -> int:
    if output_format == "json":
        combined = dict(payload) if isinstance(payload, dict) else {}
        if isinstance(fires_payload, dict):
            combined["fires"] = fires_payload.get("fires", [])
            combined["fires_total"] = fires_payload.get("total")
            combined["fires_has_more"] = fires_payload.get("has_more")
        return _print_payload(combined, "json")

    schedule = payload.get("schedule") if isinstance(payload, dict) else {}
    if not isinstance(schedule, dict):
        return 0
    timezone_name = str(schedule.get("timezone") or "UTC")
    next_fires = payload.get("next_fires") if isinstance(payload, dict) else []
    if not isinstance(next_fires, list):
        next_fires = []
    fires = fires_payload.get("fires") if isinstance(fires_payload, dict) else []
    if not isinstance(fires, list):
        fires = []

    _print_detail_section("Schedule", (
        ("ID", schedule.get("id")),
        ("Label", schedule.get("label") or "(none)"),
        ("Status", _schedule_status(schedule)),
        ("Created", _format_schedule_time(schedule.get("created"), timezone_name)),
        ("Updated", _format_schedule_time(schedule.get("updated"), timezone_name)),
    ))
    _print_detail_section("Command", (("", schedule.get("command_text")),))
    _print_detail_section("Cadence", (
        ("Preset", schedule.get("cadence_preset") or "custom"),
        ("Cron", schedule.get("cron_expr")),
        ("Timezone", timezone_name),
        ("Next run", _format_schedule_time(schedule.get("next_run_at"), timezone_name)),
        ("Next fires", "\n".join(_format_schedule_time(value, timezone_name) for value in next_fires[:3])),
    ))
    _print_detail_section("Last Fire", (
        ("Last fired", _format_schedule_time(schedule.get("last_run_at"), timezone_name) or "(never)"),
        ("Last run", schedule.get("last_run_id") or "(none)"),
        ("Failures", schedule.get("consecutive_failures")),
        ("Last error", schedule.get("last_error")),
    ))
    _print_recent_fire_table(
        fires,
        fields=("fired_at", "status", "run_id", "reason"),
        time_field="fired_at",
        timezone_name=timezone_name,
    )
    return 0


def _print_schedule_fire(payload: dict[str, Any], output_format: str) -> int:
    if output_format == "json":
        return _print_payload(payload, "json")
    schedule = payload.get("schedule") if isinstance(payload, dict) else {}
    if isinstance(schedule, dict):
        _print_table([schedule], ("id", "enabled", "last_run_at", "last_run_id", "command_text"))
    status = payload.get("status") if isinstance(payload, dict) else ""
    fired_at = payload.get("fired_at") if isinstance(payload, dict) else ""
    if status or fired_at:
        print(f"fire: {status} {fired_at}".rstrip())
    return 0


def _schedule_status(schedule: dict[str, Any]) -> str:
    if schedule.get("enabled"):
        return "active"
    reason = str(schedule.get("paused_reason") or "").strip()
    return f"paused ({reason})" if reason else "paused"


def _print_detail_section(title: str, rows: tuple[tuple[str, Any], ...]) -> None:
    print(title)
    labels = [label for label, value in rows if label and _format_detail_value(value)]
    label_width = max((len(label) for label in labels), default=0)
    for label, value in rows:
        rendered = _format_detail_value(value)
        if not rendered:
            continue
        if not label:
            print(f"  {rendered}")
            continue
        if "\n" in rendered:
            first, *rest = rendered.splitlines()
            print(f"  {label + ':':<{label_width + 1}}  {first}")
            for line in rest:
                print(f"  {'':<{label_width + 1}}  {line}")
        else:
            print(f"  {label + ':':<{label_width + 1}}  {rendered}")
    print()


def _format_detail_value(value: Any) -> str:
    if value in (None, "", []):
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, separators=(",", ": "))
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _format_bool_options(options: Any) -> str:
    if not isinstance(options, dict):
        return ""
    enabled = [
        str(key).replace("_", "-")
        for key, value in sorted(options.items())
        if bool(value)
    ]
    return ", ".join(enabled) if enabled else "default"


def _watcher_policy_from_values(
    *,
    ignore_line_patterns: list[str],
    alert_after_repeated_changes: int,
    alert_signal_classes: list[str],
) -> dict[str, Any]:
    return {
        "ignore_line_patterns": [str(item) for item in ignore_line_patterns],
        "alert_after_repeated_changes": int(alert_after_repeated_changes),
        "alert_signal_classes": [str(item) for item in alert_signal_classes],
    }


def _format_watcher_policy(policy: Any) -> str:
    if not isinstance(policy, dict):
        return ""
    patterns = [str(item) for item in policy.get("ignore_line_patterns") or []]
    repeated = int(policy.get("alert_after_repeated_changes") or 1)
    classes = [str(item) for item in policy.get("alert_signal_classes") or []]
    parts: list[str] = []
    if patterns:
        parts.append("ignore-line-patterns: " + ", ".join(patterns))
    if repeated != 1:
        parts.append(f"alert-after-repeated-changes: {repeated}")
    if classes:
        parts.append("alert-signal-classes: " + ", ".join(classes))
    return "; ".join(parts) if parts else "default"


def _print_recent_fire_table(
    fires: list[Any],
    *,
    fields: tuple[str, ...],
    time_field: str,
    timezone_name: str,
) -> None:
    print("Recent Fires")
    recent_fires = []
    for fire in fires:
        if not isinstance(fire, dict):
            continue
        recent_fires.append({
            **fire,
            time_field: _format_schedule_time(fire.get(time_field), timezone_name),
        })
    if recent_fires:
        _print_table(recent_fires, fields)
    else:
        print("  none")


def _format_schedule_time(value: Any, timezone_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
        local = parsed.astimezone(ZoneInfo(timezone_name or "UTC"))
    except (ValueError, ZoneInfoNotFoundError):
        return text
    return local.strftime("%Y-%m-%d %H:%M:%S %Z")


def _watch(client: DarklabClient, args: argparse.Namespace) -> int:
    match args.watch_command:
        case "list":
            payload = client.request("GET", "/watchers", params=_page_window_params(args))
            return _print_collection(
                payload,
                "watchers",
                args.format,
                fields=("id", "state", "project_id", "baseline_run_id", "label", "command_text"),
            )
        case "create":
            create_args = _watch_create_args(_watch_create_argv(args))
            if not create_args.first_run and not create_args.baseline_run_id:
                raise DarklabCliError("watch create needs a baseline run id, or use --first-run with -- COMMAND.")
            body: dict[str, Any] = {
                "baseline_mode": "first_run" if create_args.first_run else "existing_run",
                "baseline_run_id": "" if create_args.first_run else create_args.baseline_run_id,
                "cron_expr": create_args.cron,
                "cadence_preset": create_args.every,
                "label": create_args.label,
                "project_id": create_args.project_id,
                "timezone": create_args.timezone,
                "enabled": not create_args.disabled,
                "options": {
                    "suppress_removals": bool(create_args.suppress_removals),
                    "notify_metadata_changes": bool(create_args.notify_metadata_changes),
                },
                "policy": _watcher_policy_from_values(
                    ignore_line_patterns=list(create_args.ignore_line_pattern or []),
                    alert_after_repeated_changes=create_args.alert_after_repeated_changes,
                    alert_signal_classes=list(create_args.alert_signal_class or []),
                ),
            }
            if create_args.command_override:
                command = str(create_args.command_override or "").strip()
                body["command"] = command
            if create_args.first_run and not body.get("command"):
                raise DarklabCliError("watch create --first-run needs a command after --.")
            return _print_watcher(client.request("POST", "/watchers", body=body), create_args.format)
        case "info":
            watcher_payload = client.request("GET", f"/watchers/{args.watcher_id}")
            fires_payload = client.request("GET", f"/watchers/{args.watcher_id}/fires", params={"limit": 5, "offset": 0})
            return _print_watcher_info(watcher_payload, fires_payload, args.format)
        case "pause":
            payload = client.request(
                "PATCH",
                f"/watchers/{args.watcher_id}",
                body={"state": "paused", "reason": "operator paused"},
            )
            return _print_watcher(payload, args.format)
        case "resume":
            payload = client.request("PATCH", f"/watchers/{args.watcher_id}", body={"resume": True})
            return _print_watcher(payload, args.format)
        case "delete":
            return _print_payload(client.request("DELETE", f"/watchers/{args.watcher_id}"), args.format)
        case "run":
            return _print_watcher_fire(client.request("POST", f"/watchers/{args.watcher_id}/run-now"), args.format)
        case "accept":
            body = {"run_id": args.run_id} if args.run_id else {}
            return _print_watcher(
                client.request("POST", f"/watchers/{args.watcher_id}/accept-baseline", body=body),
                args.format,
            )
        case "set-project":
            project_id = "" if args.clear else str(args.project_id or "").strip()
            if not args.clear and not project_id:
                raise DarklabCliError("watch set-project needs a project id, or use --clear.")
            payload = client.request("PATCH", f"/watchers/{args.watcher_id}", body={"project_id": project_id})
            return _print_watcher(payload, args.format)
        case "set-policy":
            if args.clear_ignore_line_patterns and args.ignore_line_pattern:
                raise DarklabCliError("watch set-policy cannot combine --clear-ignore-line-patterns with --ignore-line-pattern.")
            if args.clear_alert_signal_classes and args.alert_signal_class:
                raise DarklabCliError("watch set-policy cannot combine --clear-alert-signal-classes with --alert-signal-class.")
            has_policy_change = any((
                args.clear_ignore_line_patterns,
                bool(args.ignore_line_pattern),
                args.alert_after_repeated_changes is not None,
                bool(args.alert_signal_class),
                args.clear_alert_signal_classes,
            ))
            if not has_policy_change:
                raise DarklabCliError("watch set-policy needs at least one policy flag.")
            current_payload = client.request("GET", f"/watchers/{args.watcher_id}")
            watcher = current_payload.get("watcher") if isinstance(current_payload, dict) else {}
            current_policy = watcher.get("policy") if isinstance(watcher, dict) else {}
            if not isinstance(current_policy, dict):
                current_policy = {}
            ignore_line_patterns = list(current_policy.get("ignore_line_patterns") or [])
            if args.clear_ignore_line_patterns:
                ignore_line_patterns = []
            elif args.ignore_line_pattern:
                ignore_line_patterns = list(args.ignore_line_pattern)
            alert_after_repeated_changes = (
                args.alert_after_repeated_changes
                if args.alert_after_repeated_changes is not None
                else int(current_policy.get("alert_after_repeated_changes") or 1)
            )
            alert_signal_classes = list(current_policy.get("alert_signal_classes") or [])
            if args.clear_alert_signal_classes:
                alert_signal_classes = []
            elif args.alert_signal_class:
                alert_signal_classes = list(args.alert_signal_class)
            policy = _watcher_policy_from_values(
                ignore_line_patterns=ignore_line_patterns,
                alert_after_repeated_changes=alert_after_repeated_changes,
                alert_signal_classes=alert_signal_classes,
            )
            payload = client.request("PATCH", f"/watchers/{args.watcher_id}", body={"policy": policy})
            return _print_watcher(payload, args.format)
        case "fires":
            payload = client.request("GET", f"/watchers/{args.watcher_id}/fires", params=_page_window_params(args))
            return _print_collection(
                payload,
                "fires",
                args.format,
                fields=("created", "fire_kind", "state_reason", "ack_state", "diff_kind", "state_at_fire", "run_id"),
            )
    return die("unknown watch command")


def _print_watcher(payload: dict[str, Any], output_format: str) -> int:
    if output_format == "json":
        return _print_payload(payload, "json")
    watcher = payload.get("watcher") if isinstance(payload, dict) else {}
    if isinstance(watcher, dict):
        _print_table([watcher], ("id", "state", "project_id", "baseline_run_id", "last_run_id", "label", "command_text"))
    return 0


def _watcher_status(watcher: dict[str, Any]) -> str:
    state = str(watcher.get("state") or "").strip() or "unknown"
    reason = str(watcher.get("state_reason") or "").strip()
    return f"{state} ({reason})" if reason else state


def _print_watcher_info(payload: dict[str, Any], fires_payload: dict[str, Any], output_format: str) -> int:
    if output_format == "json":
        combined = dict(payload) if isinstance(payload, dict) else {}
        if isinstance(fires_payload, dict):
            combined["fires"] = fires_payload.get("fires", [])
            combined["fires_total"] = fires_payload.get("total")
            combined["fires_has_more"] = fires_payload.get("has_more")
        return _print_payload(combined, "json")

    watcher = payload.get("watcher") if isinstance(payload, dict) else {}
    if not isinstance(watcher, dict):
        return 0
    schedule = watcher.get("schedule")
    if not isinstance(schedule, dict):
        schedule = {}
    timezone_name = str(schedule.get("timezone") or "UTC")
    fires = fires_payload.get("fires") if isinstance(fires_payload, dict) else []
    if not isinstance(fires, list):
        fires = []

    _print_detail_section("Watcher", (
        ("ID", watcher.get("id")),
        ("Label", watcher.get("label") or "(none)"),
        ("Project", watcher.get("project_id") or "(none)"),
        ("Status", _watcher_status(watcher)),
        ("Created", _format_schedule_time(watcher.get("created"), timezone_name)),
        ("Updated", _format_schedule_time(watcher.get("updated"), timezone_name)),
    ))
    _print_detail_section("Command", (("", watcher.get("command_text")),))
    _print_detail_section("Baseline", (
        ("Baseline run", watcher.get("baseline_run_id") or "(pending first run)"),
        ("Last run", watcher.get("last_run_id") or "(none)"),
        ("Last diff", watcher.get("last_diff_summary")),
    ))
    _print_detail_section("Cadence", (
        ("Preset", schedule.get("cadence_preset") or "custom"),
        ("Cron", schedule.get("cron_expr")),
        ("Timezone", timezone_name),
        ("Next run", _format_schedule_time(schedule.get("next_run_at"), timezone_name)),
    ))
    _print_detail_section("Health", (
        ("No-change streak", watcher.get("consecutive_no_change")),
        ("Changed streak", watcher.get("consecutive_changed")),
        ("Failures", watcher.get("consecutive_failures")),
        ("Options", _format_bool_options(watcher.get("options"))),
        ("Policy", _format_watcher_policy(watcher.get("policy"))),
        ("Last error", watcher.get("last_error")),
    ))
    _print_recent_fire_table(
        fires,
        fields=("created", "fire_kind", "state_reason", "ack_state", "diff_kind", "state_at_fire", "baseline_run_id", "run_id"),
        time_field="created",
        timezone_name=timezone_name,
    )
    return 0


def _print_watcher_fire(payload: dict[str, Any], output_format: str) -> int:
    if output_format == "json":
        return _print_payload(payload, "json")
    watcher = payload.get("watcher") if isinstance(payload, dict) else {}
    if isinstance(watcher, dict):
        _print_table([watcher], ("id", "state", "baseline_run_id", "last_run_id", "command_text"))
    status = payload.get("status") if isinstance(payload, dict) else ""
    fired_at = payload.get("fired_at") if isinstance(payload, dict) else ""
    if status or fired_at:
        print(f"fire: {status} {fired_at}".rstrip())
    return 0


def _notify(client: DarklabClient, args: argparse.Namespace) -> int:
    match args.notify_command:
        case "list":
            payload = client.request("GET", "/notification-channels")
            return _print_collection(payload, "channels", args.format, fields=("id", "kind", "muted", "label"))
        case "create":
            body = {
                "kind": args.kind,
                "label": args.label,
                "triggers": args.trigger,
                "config": _parse_key_values(args.config),
                "secret_values": _notification_secret_values(client, args.kind, args.secret_file),
            }
            payload = client.request("POST", "/notification-channels", body=body)
            return _print_notification_channel(payload, args.format)
        case "update":
            body: dict[str, Any] = {}
            if args.label is not None:
                body["label"] = args.label
            if args.trigger:
                body["triggers"] = args.trigger
            if args.config:
                body["config"] = _parse_key_values(args.config)
            if not body:
                raise DarklabCliError("notify update needs at least one of --label, --trigger, or --config.")
            payload = client.request("PATCH", f"/notification-channels/{args.channel_id}", body=body)
            return _print_notification_channel(payload, args.format)
        case "mute":
            payload = client.request("PATCH", f"/notification-channels/{args.channel_id}", body={"muted": True})
            return _print_notification_channel(payload, args.format)
        case "unmute":
            payload = client.request("PATCH", f"/notification-channels/{args.channel_id}", body={"muted": False})
            return _print_notification_channel(payload, args.format)
        case "delete":
            return _print_payload(client.request("DELETE", f"/notification-channels/{args.channel_id}"), args.format)
        case "test":
            payload = client.request("POST", f"/notification-channels/{args.channel_id}/test")
            if args.format == "json":
                return _print_payload(payload, "json")
            print(f"queued: {payload.get('queued', 0)}")
            for event_id in payload.get("event_ids", []):
                print(event_id)
            return 0
        case "events":
            payload = client.request("GET", "/notification-events", params={
                "status": args.status,
                "channel_id": args.channel_id,
                "trigger": args.trigger,
                "limit": args.limit,
                "offset": args.offset,
            })
            return _print_collection(
                payload,
                "events",
                args.format,
                fields=("created", "id", "status", "trigger", "channel_id", "run_id"),
            )
    return die("unknown notify command")


def _print_notification_channel(payload: dict[str, Any], output_format: str) -> int:
    if output_format == "json":
        return _print_payload(payload, "json")
    channel = payload.get("channel") if isinstance(payload, dict) else {}
    if isinstance(channel, dict):
        _print_table([channel], ("id", "kind", "muted", "label"))
    return 0


def _parse_key_values(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise DarklabCliError("--config values must use KEY=VALUE.")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise DarklabCliError("--config keys cannot be empty.")
        parsed[key] = value.strip()
    return parsed


def _notification_secret_field_names(client: DarklabClient, kind: str) -> tuple[str, ...]:
    payload = client.request("GET", "/notification-channel-kinds")
    kinds = payload.get("kinds") if isinstance(payload, dict) else []
    for item in kinds if isinstance(kinds, list) else []:
        if not isinstance(item, dict) or item.get("kind") != kind:
            continue
        fields = item.get("secret_fields")
        if not isinstance(fields, list):
            return ()
        return tuple(
            str(field.get("name") or "").strip()
            for field in fields
            if isinstance(field, dict) and str(field.get("name") or "").strip()
        )
    raise DarklabCliError(f"unsupported notification channel kind: {kind}")


def _notification_secret_values(client: DarklabClient, kind: str, secret_file: str | None) -> dict[str, str]:
    expected = _notification_secret_field_names(client, kind)
    if not expected:
        return {}
    if secret_file:
        path = Path(secret_file)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise DarklabCliError(f"could not read secret file: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise DarklabCliError(f"secret file must be JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise DarklabCliError("secret file must contain a JSON object.")
        values = {field: str(raw.get(field) or "") for field in expected}
    else:
        values = {field: getpass.getpass(f"{kind} {field}: ") for field in expected}
    missing = [field for field in expected if not str(values.get(field) or "").strip()]
    if missing:
        raise DarklabCliError(f"missing secret field(s): {', '.join(missing)}")
    return values


def _atlas(client: DarklabClient, args: argparse.Namespace) -> int:
    match args.atlas_command:
        case "summary":
            return _print_atlas_summary(client.request("GET", "/atlas", params=_atlas_filter_params(args)), args.format)
        case "runs":
            payload = client.request("GET", "/atlas/runs", params={
                "q": args.q,
                "run_id": args.run_id,
                "limit": args.limit,
            })
            return _print_collection(payload, "runs", args.format, fields=("id", "entity_count", "finding_count", "command"))
        case "entities":
            payload = client.request("GET", "/atlas/entities", params={**_atlas_filter_params(args), **_page_window_params(args)})
            return _print_collection(
                payload,
                "entities",
                args.format,
                fields=("type", "id", "occurrence_count", "canonical_value"),
            )
        case "entity":
            payload = client.request("GET", f"/atlas/entities/{args.entity_id}")
            if args.format == "json":
                return _print_payload(payload, "json")
            entity = payload.get("entity") if isinstance(payload, dict) else {}
            if isinstance(entity, dict):
                _print_table([entity], ("type", "id", "occurrence_count", "canonical_value"))
            return 0
        case "findings":
            params = {**_atlas_filter_params(args), **_page_window_params(args), "review_state": args.review_state}
            payload = client.request("GET", "/atlas/findings", params=params)
            return _print_collection(payload, "findings", args.format, fields=("id", "status", "severity", "title"))
        case "finding":
            payload = client.request("GET", f"/atlas/findings/{args.finding_id}")
            if args.format == "json":
                return _print_payload(payload, "json")
            finding = payload.get("finding") if isinstance(payload, dict) else {}
            if isinstance(finding, dict):
                _print_table([finding], ("id", "status", "severity", "title"))
            return 0
    return die("unknown atlas command")


def _atlas_filter_params(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "q": getattr(args, "q", None),
        "project_id": getattr(args, "project_id", None),
        "run_id": getattr(args, "run_id", None),
        "entity_type": getattr(args, "entity_type", None),
        "orphan_filter": getattr(args, "orphan_filter", None),
        "suppression_filter": getattr(args, "suppression_filter", None),
    }


def _print_atlas_summary(payload: dict[str, Any], output_format: str) -> int:
    if output_format == "json":
        return _print_payload(payload, "json")
    counts = payload.get("counts") if isinstance(payload, dict) else {}
    if not isinstance(counts, dict):
        counts = {}
    print(f"entities: {payload.get('total', 0)}")
    print(f"findings: {payload.get('findings', 0)}")
    for entity_type in sorted(counts):
        print(f"{entity_type}: {counts[entity_type]}")
    return 0


def _run(client: DarklabClient, args: argparse.Namespace) -> int:
    if args.project_id and args.link_project:
        return die("--project and --link-project cannot be used together.")
    if args.follow and args.format == "json":
        if not args.wait:
            return die(
                "--format json is start-only; use --no-follow --format json, "
                "--wait --format json, or --format ndjson to stream events."
            )
    if not args.follow and args.format == "ndjson":
        return die("--format ndjson is stream-only; remove --no-follow or use --format json.")
    if args.wait and args.format == "ndjson":
        return die("--format ndjson is stream-only; remove --wait or use --format json.")
    project_id = args.project_id or (_resolve_project_id(client, args.link_project) if args.link_project else None)
    payload = client.request(
        "POST",
        "/runs",
        body={"command": args.run_command, "project_id": project_id},
    )
    if args.wait:
        wait_params = {"timeout": args.wait_timeout}
        waited = client.request("POST", f"/runs/{payload['id']}/wait", params=wait_params)
        return _print_wait_result(waited, args.format)
    if not args.follow:
        return _print_payload(payload, args.format)
    return _tail(client, payload["id"], "ndjson" if args.format == "ndjson" else "text", started_by_run=True)


def _active(client: DarklabClient, args: argparse.Namespace) -> int:
    payload = client.request("GET", "/runs")
    return _print_collection(payload, "runs", args.format, fields=("started", "id", "status", "run_kind", "command"))


def _resolve_project_id(client: DarklabClient, name_or_id: object) -> str:
    needle = str(name_or_id or "").strip()
    if not needle:
        raise DarklabCliError("--link-project requires a project name.")
    matches: list[dict[str, Any]] = []
    offset = 0
    while True:
        payload = client.request("GET", "/projects", params={"limit": 100, "offset": offset})
        projects = payload.get("projects") if isinstance(payload, dict) else []
        if not isinstance(projects, list):
            break
        for project in projects:
            if not isinstance(project, dict):
                continue
            if str(project.get("id") or "") == needle:
                return str(project["id"])
            if str(project.get("name") or "").casefold() == needle.casefold():
                matches.append(project)
        offset += len(projects)
        if not payload.get("has_more") or not projects:
            break
    if len(matches) == 1:
        return str(matches[0]["id"])
    if matches:
        raise DarklabCliError(f"--link-project is ambiguous: {needle}")
    raise DarklabCliError(f"project not found: {needle}")


def _print_wait_result(payload: dict[str, Any], output_format: str) -> int:
    if output_format == "json":
        return _print_payload(payload, "json")
    run = payload.get("run") if isinstance(payload, dict) else {}
    if not isinstance(run, dict):
        return die("wait response did not include a run payload.")
    print("  ".join(str(run.get(field, "")) for field in ("id", "status", "exit_code", "command")))
    return _exit_code_from_run(run)


def _tail(client: DarklabClient, run_id: str, output_format: str, *, after: str = "", started_by_run: bool = False) -> int:
    try:
        if output_format == "ndjson":
            response = client.request("GET", f"/runs/{run_id}/stream", params={"format": "ndjson", "after": after}, stream=True)
            exit_code = 0
            terminal_seen = False
            for raw in response:
                line = raw.decode("utf-8", errors="replace")
                print(line, end="")
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                exit_code = _exit_code_from_event(payload, exit_code)
                terminal_seen = terminal_seen or _is_terminal_event(payload)
            if not terminal_seen:
                return _stream_incomplete(run_id)
            return exit_code

        response = client.request("GET", f"/runs/{run_id}/stream", params={"after": after}, stream=True)
        exit_code = 0
        terminal_seen = False
        for event in iter_sse_events(response):
            if event.get("type") == "output_batch" and isinstance(event.get("lines"), list):
                for line_event in event["lines"]:
                    if isinstance(line_event, dict) and line_event.get("text") is not None:
                        sys.stdout.write(str(line_event.get("text")).rstrip("\r\n") + "\n")
            elif event.get("type") in {"output", "notice"} and event.get("text") is not None:
                sys.stdout.write(str(event.get("text")).rstrip("\r\n") + "\n")
            exit_code = _exit_code_from_event(event, exit_code)
            terminal_seen = terminal_seen or _is_terminal_event(event)
        if not terminal_seen:
            return _stream_incomplete(run_id)
        return exit_code
    except KeyboardInterrupt:
        return _stream_interrupted(run_id, started_by_run=started_by_run)


def _stream_incomplete(run_id: str) -> int:
    print(f"run stream ended before {run_id} reached a terminal event", file=sys.stderr)
    return STREAM_INCOMPLETE_EXIT_CODE


def _stream_interrupted(run_id: str, *, started_by_run: bool) -> int:
    if started_by_run:
        print(
            f"stopped following run {run_id}; use `darklab tail {run_id}` to reattach "
            f"or `darklab cancel {run_id}` to stop it.",
            file=sys.stderr,
        )
    else:
        print(f"stopped following run {run_id}", file=sys.stderr)
    return STREAM_INTERRUPTED_EXIT_CODE


def _is_terminal_event(event: dict[str, Any]) -> bool:
    return str(event.get("type") or event.get("event") or "") in {"exit", "error", "killed"}


def _exit_code_from_event(event: dict[str, Any], current: int) -> int:
    event_type = str(event.get("type") or event.get("event") or "")
    if event_type == "exit":
        try:
            return int(event.get("code") or 0)
        except (TypeError, ValueError):
            return 1
    if event_type in {"error", "killed"}:
        return 1
    return current


def _exit_code_from_run(run: dict[str, Any]) -> int:
    status = str(run.get("status") or "")
    if status in {"failed", "killed", "error"}:
        return 1
    if run.get("exit_code") is None:
        return 0
    try:
        return int(run.get("exit_code") or 0)
    except (TypeError, ValueError):
        return 1


def _page_params(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "project_id": getattr(args, "project_id", None),
        "since": getattr(args, "since", None),
        "until": getattr(args, "until", None),
        "limit": getattr(args, "limit", None),
        "offset": getattr(args, "offset", None),
    }


def _history_params(args: argparse.Namespace) -> dict[str, Any]:
    params = _page_params(args)
    history_type = str(getattr(args, "history_type", "") or "").strip().lower()
    run_kind = {
        "external": "external",
        "runs_external": "external",
        "builtin": "builtin",
        "runs_builtin": "builtin",
    }.get(history_type, "")
    if run_kind:
        params["run_kind"] = run_kind
    return params


def _structured_selector_params(args: argparse.Namespace) -> dict[str, Any]:
    params = {}
    for key in ("signal", "kind", "role", "entity"):
        value = getattr(args, key, None)
        if value:
            params[key] = value
    if getattr(args, "not_kind", None):
        params["not_kind"] = args.not_kind
    if getattr(args, "entity_type", None):
        params["entity_type"] = args.entity_type
    return params


def _page_window_params(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "limit": getattr(args, "limit", None),
        "offset": getattr(args, "offset", None),
    }


def _print_search_matches(payload: dict[str, Any], output_format: str) -> int:
    matches = payload.get("matches") if isinstance(payload, dict) else []
    if not isinstance(matches, list):
        matches = []
    if output_format == "json":
        print_json(payload)
        return 0
    if output_format == "ndjson":
        for match in matches:
            print(json.dumps(match, sort_keys=True))
        return 0
    for index, match in enumerate(matches):
        if not isinstance(match, dict):
            continue
        run_id = str(match.get("run_id") or "")
        try:
            line_number = int(match.get("line_number") or 0)
        except (TypeError, ValueError):
            line_number = 0
        before_value = match.get("context_before")
        after_value = match.get("context_after")
        before: list[Any] = before_value if isinstance(before_value, list) else []
        after: list[Any] = after_value if isinstance(after_value, list) else []
        before_start = line_number - len(before)
        for offset, line in enumerate(before):
            print(f"{run_id}:{before_start + offset}- {line}")
        print(f"{run_id}:{line_number}: {match.get('line', '')}")
        for offset, line in enumerate(after, start=1):
            print(f"{run_id}:{line_number + offset}+ {line}")
        if index < len(matches) - 1:
            print("--")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
