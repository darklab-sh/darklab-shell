# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""App-owned autocomplete grammar for registered helper commands."""

from __future__ import annotations


BUILTIN_AUTOCOMPLETE_REGISTRY = {
    "version": 1,
    "commands": [
        {"root": "banner", "description": "built-in: print the configured banner art", "autocomplete": {"arguments": []}},
        {
            "root": "cat",
            "description": "built-in: show a session file",
            "feature_required": "workspace",
            "autocomplete": {"argument_limit": 1, "arguments": []},
        },
        {
            "root": "cd",
            "description": "built-in: change the current workspace folder",
            "feature_required": "workspace",
            "autocomplete": {"argument_limit": 1, "arguments": []},
        },
        {"root": "clear", "description": "built-in: clear the current terminal tab output", "autocomplete": {"arguments": []}},
        {
            "root": "commands",
            "description": "built-in: list built-in and allowed external commands",
            "autocomplete": {
                "flags": [
                    {"value": "--built-in", "description": "Show only built-in shell commands"},
                    {"value": "--external", "description": "Show only allowed external commands"},
                ],
                "subcommands": [
                    {
                        "value": "info",
                        "description": "Show details for one supported command",
                        "takes_value": True,
                        "insert": "info ",
                    }
                ],
            },
        },
        {
            "root": "config",
            "description": "built-in: show or update user options",
            "autocomplete": {
                "subcommands": [
                    {"value": "list", "description": "Show all current user config", "closes": True},
                    {"value": "get", "description": "Show one user config value", "takes_value": True, "insert": "get "},
                    {"value": "set", "description": "Set one user config value", "takes_value": True, "insert": "set "},
                ]
            },
        },
        {"root": "date", "description": "built-in: show the current server time", "autocomplete": {"arguments": []}},
        {
            "root": "diff",
            "description": "built-in: compare session files or completed run output",
            "autocomplete": {
                "flags": [
                    {"value": "--last", "description": "Compare the last two completed runs in this tab"},
                    {"value": "-q", "description": "Only report whether the sources differ"},
                    {"value": "--brief", "description": "Only report whether the sources differ"},
                    {"value": "-u", "description": "Show a unified comparison with - and + lines"},
                    {"value": "--unified", "description": "Show a unified comparison with - and + lines"},
                    {"value": "-y", "description": "Show both sources in side-by-side columns"},
                    {"value": "--side-by-side", "description": "Show both sources in side-by-side columns"},
                ],
                "argument_limit": 2,
                "arguments": [],
            },
        },
        {
            "root": "df",
            "description": "built-in: show a compact filesystem summary",
            "autocomplete": {"flags": [{"value": "-h", "description": "Human-readable disk usage"}]},
        },
        {
            "root": "env",
            "description": "built-in: show core environment values for this shell",
            "autocomplete": {"arguments": []},
        },
        {"root": "exit", "description": "built-in: close the current tab", "autocomplete": {"arguments": []}},
        {"root": "faq", "description": "built-in: show configured FAQ entries", "autocomplete": {"arguments": []}},
        {
            "root": "file",
            "description": "built-in: list, view, compare, create, edit, download, copy, move, or remove session files",
            "feature_required": "workspace",
            "autocomplete": {
                "subcommands": [
                    {
                        "value": "list",
                        "description": "List current session files",
                        "takes_value": True,
                        "insert": "list ",
                        "value_hint": {"value": "<folder>", "hint_only": True, "description": "Session folder"},
                    },
                    {
                        "value": "ls",
                        "description": "List current session files",
                        "takes_value": True,
                        "insert": "ls ",
                        "value_hint": {"value": "<folder>", "hint_only": True, "description": "Session folder"},
                    },
                    {
                        "value": "show",
                        "description": "Print a session file in the terminal",
                        "takes_value": True,
                        "insert": "show ",
                        "value_hint": {"value": "<file>", "hint_only": True, "description": "Session file"},
                    },
                    {
                        "value": "diff",
                        "description": "Compare files or completed run output",
                        "takes_value": True,
                        "insert": "diff ",
                        "value_hint": {
                            "value": "<source1> <source2>",
                            "hint_only": True,
                            "description": "Files, run:<run-id> sources, or one of each",
                        },
                    },
                    {
                        "value": "add",
                        "description": "Open the Files editor for a new session file",
                        "takes_value": True,
                        "insert": "add ",
                        "value_hint": {"value": "<file>", "hint_only": True, "description": "New session file name"},
                    },
                    {
                        "value": "add-dir",
                        "description": "Create a session folder",
                        "takes_value": True,
                        "insert": "add-dir ",
                        "value_hint": {"value": "<folder>", "hint_only": True, "description": "New session folder"},
                    },
                    {
                        "value": "edit",
                        "description": "Open the Files editor for an existing session file",
                        "takes_value": True,
                        "insert": "edit ",
                        "value_hint": {"value": "<file>", "hint_only": True, "description": "Session file"},
                    },
                    {
                        "value": "download",
                        "description": "Download a session file through the browser",
                        "takes_value": True,
                        "insert": "download ",
                        "value_hint": {"value": "<file>", "hint_only": True, "description": "Session file"},
                    },
                    {
                        "value": "move",
                        "description": "Move or rename a session file or folder",
                        "takes_value": True,
                        "insert": "move ",
                        "value_hint": {
                            "value": "<source> <destination>",
                            "hint_only": True,
                            "value_type": "workspace_path",
                            "description": "Session file or folder path",
                        },
                    },
                    {
                        "value": "copy",
                        "description": "Copy a session file",
                        "takes_value": True,
                        "insert": "copy ",
                        "value_hint": {
                            "value": "<source> <destination>",
                            "hint_only": True,
                            "value_type": "workspace_path",
                            "description": "Source file and destination path",
                        },
                    },
                    {
                        "value": "touch",
                        "description": "Create an empty session file or update its timestamp",
                        "takes_value": True,
                        "insert": "touch ",
                        "value_hint": {
                            "value": "<file>",
                            "hint_only": True,
                            "value_type": "workspace_path",
                            "description": "Session file path",
                        },
                    },
                    {
                        "value": "rm",
                        "description": "Remove a session file from this session",
                        "takes_value": True,
                        "hidden": True,
                        "insert": "rm ",
                        "value_hint": {"value": "<file>", "hint_only": True, "description": "Session file"},
                    },
                    {
                        "value": "delete",
                        "description": "Remove a session file from this session",
                        "takes_value": True,
                        "insert": "delete ",
                        "value_hint": {"value": "<file>", "hint_only": True, "description": "Session file"},
                    },
                    {"value": "help", "description": "Show file command usage", "closes": True},
                ]
            },
        },
        {
            "root": "fortune",
            "description": "built-in: print a short operator-themed one-liner",
            "autocomplete": {"arguments": []},
        },
        {
            "root": "free",
            "description": "built-in: show a compact memory summary",
            "autocomplete": {"flags": [{"value": "-h", "description": "Human-readable memory usage"}]},
        },
        {"root": "groups", "description": "built-in: show the shell group membership", "autocomplete": {"arguments": []}},
        {
            "root": "grep",
            "description": "built-in: filter a session file",
            "feature_required": "workspace",
            "autocomplete": {
                "flags": [
                    {"value": "-i", "description": "Ignore case"},
                    {"value": "-v", "description": "Invert match"},
                    {"value": "-E", "description": "Extended regex"},
                ],
                "argument_limit": 2,
                "arguments": [],
            },
        },
        {
            "root": "head",
            "description": "built-in: print the first lines of a session file",
            "feature_required": "workspace",
            "autocomplete": {
                "flags": [
                    {
                        "value": "-n",
                        "description": "Line count",
                        "takes_value": True,
                        "suggest": [{"value": "10", "description": "Ten lines"}],
                    }
                ],
                "argument_limit": 1,
                "arguments": [],
            },
        },
        {
            "root": "help",
            "description": "built-in: show README, FAQ, shortcuts, and command-discovery guidance",
            "autocomplete": {"arguments": []},
        },
        {"root": "history", "description": "built-in: list command history from this session", "autocomplete": {"arguments": []}},
        {
            "root": "hostname",
            "description": "built-in: show the configured shell instance name",
            "autocomplete": {"arguments": []},
        },
        {"root": "id", "description": "built-in: show the shell identity", "autocomplete": {"arguments": []}},
        {
            "root": "intel",
            "description": "built-in: query app-native external intel providers",
            "autocomplete": {
                "subcommands": [
                    {
                        "value": "ip",
                        "description": "Look up an IP address",
                        "takes_value": True,
                        "insert": "ip ",
                        "value_hint": {"value": "<ip>", "hint_only": True, "value_type": "ip", "description": "IP address"},
                    },
                    {
                        "value": "domain",
                        "description": "Look up a domain",
                        "takes_value": True,
                        "insert": "domain ",
                        "value_hint": {"value": "<domain>", "hint_only": True, "value_type": "domain", "description": "Domain"},
                    },
                    {
                        "value": "url",
                        "description": "Look up a URL",
                        "takes_value": True,
                        "insert": "url ",
                        "value_hint": {"value": "<url>", "hint_only": True, "value_type": "url", "description": "URL"},
                    },
                    {
                        "value": "hash",
                        "description": "Look up a file hash",
                        "takes_value": True,
                        "insert": "hash ",
                        "value_hint": {"value": "<md5|sha1|sha256>", "hint_only": True, "description": "File hash"},
                    },
                    {
                        "value": "cve",
                        "description": "Look up a CVE",
                        "takes_value": True,
                        "insert": "cve ",
                        "value_hint": {"value": "<CVE-ID>", "hint_only": True, "value_type": "cve", "description": "CVE ID"},
                    },
                ],
                "flags": [{"value": "--include-private", "description": "Allow private or loopback IP lookups"}],
            },
        },
        {
            "root": "ip",
            "description": "built-in: show a minimal shell network interface view",
            "autocomplete": {"arguments": [{"value": "a", "description": "Show all network interfaces and addresses"}]},
        },
        {
            "root": "jobs",
            "description": "built-in: alias for runs",
            "autocomplete": {
                "flags": [
                    {"value": "-v", "description": "Show full IDs, started timestamps, and metadata source"},
                    {"value": "--verbose", "description": "Show full IDs, started timestamps, and metadata source"},
                    {"value": "--json", "description": "Print active-run metadata as JSON"},
                ]
            },
        },
        {
            "root": "last",
            "description": "built-in: show recent completed runs with timestamps and exit codes",
            "autocomplete": {"arguments": []},
        },
        {
            "root": "limits",
            "description": "built-in: show configured runtime, history, and retention limits",
            "autocomplete": {"arguments": []},
        },
        {
            "root": "ll",
            "description": "built-in: long-list session files",
            "feature_required": "workspace",
            "autocomplete": {
                "flags": [{"value": "-R", "description": "Recursive listing"}],
                "argument_limit": 1,
                "arguments": [],
            },
        },
        {
            "root": "ls",
            "description": "built-in: list session files",
            "feature_required": "workspace",
            "autocomplete": {
                "flags": [{"value": "-l", "description": "Long listing"}, {"value": "-R", "description": "Recursive listing"}],
                "argument_limit": 1,
                "arguments": [],
            },
        },
        {
            "root": "mkdir",
            "description": "built-in: create a session folder",
            "feature_required": "workspace",
            "autocomplete": {"argument_limit": 1, "arguments": []},
        },
        {
            "root": "cp",
            "description": "built-in: copy a session file",
            "feature_required": "workspace",
            "autocomplete": {
                "argument_limit": 2,
                "arguments": [
                    {
                        "value": "<source> <destination>",
                        "hint_only": True,
                        "value_type": "workspace_path",
                        "description": "Source file and destination path",
                    }
                ],
            },
        },
        {
            "root": "mv",
            "description": "built-in: move or rename a session file or folder",
            "feature_required": "workspace",
            "autocomplete": {
                "argument_limit": 2,
                "arguments": [
                    {
                        "value": "<source> <destination>",
                        "hint_only": True,
                        "value_type": "workspace_path",
                        "description": "Session file or folder path",
                    }
                ],
            },
        },
        {
            "root": "man",
            "description": "built-in: show a real or built-in manual page",
            "autocomplete": {"argument_limit": 1, "arguments": []},
        },
        {
            "root": "ps",
            "description": "built-in: show the current shell process view",
            "autocomplete": {
                "flags": [
                    {"value": "aux", "description": "All processes with user and memory info"},
                    {"value": "-ef", "description": "All processes, full format"},
                ]
            },
        },
        {"root": "pwd", "description": "built-in: show the session files path", "autocomplete": {"arguments": []}},
        {
            "root": "project",
            "description": "built-in: create, select, link, and annotate project workspaces",
            "autocomplete": {
                "subcommands": {
                    "list": {
                        "description": "List current-session projects",
                        "flags": [
                            {"value": "--all", "description": "Include archived projects"},
                            {"value": "-a", "description": "Include archived projects"},
                        ],
                    },
                    "create": {
                        "description": "Create and activate a project",
                        "arguments": [{"value": "<name>", "hint_only": True, "description": "Project name"}],
                    },
                    "use": {
                        "description": "Activate an existing project",
                        "arguments": [{"value": "<name-or-id>", "hint_only": True, "description": "Project name, slug, or id"}],
                    },
                    "current": {"description": "Show the active project", "closes": True},
                    "rename": {
                        "description": "Rename a project",
                        "arguments": [
                            {"value": "<name-or-id>", "hint_only": True, "description": "Project name, slug, or id"},
                            {"value": "<new-name>", "hint_only": True, "description": "New project name"},
                        ],
                    },
                    "clear": {"description": "Clear the active project", "closes": True},
                    "archive": {
                        "description": "Archive a project",
                        "arguments": [{"value": "<name-or-id>", "hint_only": True, "description": "Project name, slug, or id"}],
                    },
                    "unarchive": {
                        "description": "Unarchive a project",
                        "arguments": [{"value": "<name-or-id>", "hint_only": True, "description": "Project name, slug, or id"}],
                    },
                    "delete": {
                        "description": "Delete a project",
                        "arguments": [{"value": "<name-or-id>", "hint_only": True, "description": "Project name, slug, or id"}],
                    },
                    "link": {
                        "description": "Link a run to the active project",
                        "subcommands": {
                            "last": {"description": "Link the latest run", "close_after": {"last": 0}},
                            "run": {
                                "description": "Link a run",
                                "arguments": [
                                    {"value": "last", "description": "Link the latest run in this tab"},
                                    {"value": "<run-id>", "hint_only": True, "description": "Run id"},
                                ],
                                "close_after": {"run": 1},
                            },
                        },
                    },
                    "unlink": {
                        "description": "Unlink a run from the active project",
                        "subcommands": {
                            "run": {
                                "description": "Unlink a run",
                                "arguments": [{"value": "<run-id>", "hint_only": True, "description": "Run id"}],
                                "close_after": {"run": 1},
                            }
                        },
                    },
                    "target": {
                        "description": "Manage active-project targets",
                        "subcommands": {
                            "list": {"description": "List project targets", "closes": True},
                            "add": {
                                "description": "Add a typed target",
                                "subcommands": {
                                    "domain": {
                                        "description": "Add a domain target",
                                        "arguments": [
                                            {
                                                "value": "<domain>",
                                                "hint_only": True,
                                                "value_type": "domain",
                                                "description": "Domain value",
                                            }
                                        ],
                                        "close_after": {"domain": 1},
                                    },
                                    "url": {
                                        "description": "Add a URL target",
                                        "arguments": [
                                            {"value": "<url>", "hint_only": True, "value_type": "url", "description": "URL value"}
                                        ],
                                        "close_after": {"url": 1},
                                    },
                                    "host": {
                                        "description": "Add a host target",
                                        "arguments": [
                                            {
                                                "value": "<host>",
                                                "hint_only": True,
                                                "value_type": "host",
                                                "description": "Host value",
                                            }
                                        ],
                                        "close_after": {"host": 1},
                                    },
                                    "ip": {
                                        "description": "Add an IP target",
                                        "arguments": [
                                            {"value": "<ip>", "hint_only": True, "value_type": "ip", "description": "IP address"}
                                        ],
                                        "close_after": {"ip": 1},
                                    },
                                    "cidr": {
                                        "description": "Add a CIDR target",
                                        "arguments": [
                                            {
                                                "value": "<cidr>",
                                                "hint_only": True,
                                                "value_type": "cidr",
                                                "description": "CIDR range",
                                            }
                                        ],
                                        "close_after": {"cidr": 1},
                                    },
                                },
                            },
                            "quick-add": {
                                "description": "Infer and add a target from text",
                                "arguments": [
                                    {
                                        "value": "<text-or-value>",
                                        "hint_only": True,
                                        "description": "Text containing a URL, CIDR, IP, or domain",
                                    }
                                ],
                            },
                            "remove": {
                                "description": "Remove a target",
                                "arguments": [{"value": "<id-or-value>", "hint_only": True, "description": "Target id or value"}],
                            },
                        },
                    },
                }
            },
        },
        {"root": "quit", "description": "built-in: close the current tab", "autocomplete": {"arguments": []}},
        {
            "root": "retention",
            "description": "built-in: show retention and persisted-output settings",
            "autocomplete": {"arguments": []},
        },
        {
            "root": "rm",
            "description": "built-in: remove a session file after confirmation",
            "feature_required": "workspace",
            "autocomplete": {
                "flags": [
                    {"value": "-r", "description": "Remove folders recursively"},
                    {"value": "-f", "description": "Force-style flag; confirmation is still required"},
                    {"value": "-rf", "description": "Remove folders recursively"},
                ],
                "argument_limit": 1,
                "arguments": [],
            },
        },
        {
            "root": "touch",
            "description": "built-in: create an empty session file or update its timestamp",
            "feature_required": "workspace",
            "autocomplete": {
                "argument_limit": 1,
                "arguments": [
                    {"value": "<file>", "hint_only": True, "value_type": "workspace_path", "description": "Session file path"}
                ],
            },
        },
        {"root": "route", "description": "built-in: show the shell routing table summary", "autocomplete": {"arguments": []}},
        {
            "root": "notify",
            "description": "built-in: manage outbound notification channels",
            "autocomplete": {
                "subcommands": {
                    "list": {"description": "List notification channels", "closes": True},
                    "kinds": {"description": "List supported notification channel types", "closes": True},
                    "create": {
                        "description": "Create a channel when no secret values are required",
                        "arguments": [
                            {"value": "webhook", "description": "Generic JSON webhook"},
                            {"value": "slack", "description": "Slack incoming webhook"},
                            {"value": "discord", "description": "Discord incoming webhook"},
                            {"value": "telegram", "description": "Telegram Bot API"},
                            {"value": "pushover", "description": "Pushover"},
                            {"value": "email", "description": "SMTP email"},
                        ],
                        "flags": [
                            {"value": "--label", "takes_value": True, "description": "Display label"},
                            {
                                "value": "--trigger",
                                "takes_value": True,
                                "description": "Notification trigger",
                                "suggest": [
                                    {"value": "run_complete", "description": "External run completed"},
                                    {"value": "pty_session_ended", "description": "PTY session ended"},
                                    {"value": "scheduled_run_failed", "description": "Scheduled run failed"},
                                    {"value": "watcher_changed", "description": "Watcher detected a change"},
                                    {"value": "watcher_error", "description": "Watcher failed"},
                                    {"value": "watcher_recovered", "description": "Watcher recovered"},
                                ],
                            },
                            {"value": "--config", "takes_value": True, "description": "Channel config as KEY=VALUE"},
                            {"value": "--muted", "description": "Create the channel muted"},
                        ],
                    },
                    "update": {
                        "description": "Update channel label, triggers, or config",
                        "arguments": [{"value": "<channel-id>", "hint_only": True, "description": "Notification channel id"}],
                        "flags": [
                            {"value": "--label", "takes_value": True, "description": "Display label"},
                            {"value": "--trigger", "takes_value": True, "description": "Replacement notification trigger"},
                            {"value": "--config", "takes_value": True, "description": "Replacement config as KEY=VALUE"},
                            {"value": "--muted", "description": "Set the channel muted"},
                        ],
                    },
                    "info": {
                        "description": "Show channel details",
                        "arguments": [{"value": "<channel-id>", "hint_only": True, "description": "Notification channel id"}],
                    },
                    "mute": {
                        "description": "Mute a channel",
                        "arguments": [{"value": "<channel-id>", "hint_only": True, "description": "Notification channel id"}],
                    },
                    "unmute": {
                        "description": "Unmute a channel",
                        "arguments": [{"value": "<channel-id>", "hint_only": True, "description": "Notification channel id"}],
                    },
                    "delete": {
                        "description": "Delete a channel",
                        "arguments": [{"value": "<channel-id>", "hint_only": True, "description": "Notification channel id"}],
                    },
                    "test": {
                        "description": "Send a test notification",
                        "arguments": [{"value": "<channel-id>", "hint_only": True, "description": "Notification channel id"}],
                    },
                    "events": {
                        "description": "List notification delivery events",
                        "flags": [
                            {"value": "--channel", "takes_value": True, "description": "Filter by channel id"},
                            {
                                "value": "--status",
                                "takes_value": True,
                                "description": "Filter by delivery status",
                                "suggest": [
                                    {"value": "pending", "description": "Pending delivery"},
                                    {"value": "retry_wait", "description": "Waiting to retry"},
                                    {"value": "sent", "description": "Sent"},
                                    {"value": "dead", "description": "Dead-lettered"},
                                ],
                            },
                            {"value": "--trigger", "takes_value": True, "description": "Filter by trigger"},
                            {"value": "--limit", "takes_value": True, "description": "Rows to return"},
                            {"value": "--offset", "takes_value": True, "description": "Rows to skip"},
                        ],
                    },
                }
            },
        },
        {
            "root": "runs",
            "description": "built-in: show active runs; use -v for details or --json for automation",
            "autocomplete": {
                "flags": [
                    {"value": "-v", "description": "Show full IDs, started timestamps, and metadata source"},
                    {"value": "--verbose", "description": "Show full IDs, started timestamps, and metadata source"},
                    {"value": "--json", "description": "Print active-run metadata as JSON"},
                ]
            },
        },
        {
            "root": "schedule",
            "description": "built-in: manage saved recurring commands",
            "autocomplete": {
                "subcommands": {
                    "list": {"description": "List current-session schedules", "closes": True},
                    "create": {
                        "description": "Create a saved schedule",
                        "flags": [
                            {
                                "value": "--cron",
                                "takes_value": True,
                                "description": "Five-field cron expression",
                                "suggest": [
                                    {"value": "0 * * * *", "description": "Every hour"},
                                    {"value": "0 0 * * *", "description": "Every day"},
                                    {"value": "0 0 * * 0", "description": "Every week"},
                                ],
                            },
                            {
                                "value": "--every",
                                "takes_value": True,
                                "description": "Cadence preset",
                                "suggest": [
                                    {"value": "hourly", "description": "Every hour"},
                                    {"value": "daily", "description": "Every day"},
                                    {"value": "weekly", "description": "Every week"},
                                ],
                            },
                            {"value": "--label", "takes_value": True, "description": "Display label"},
                            {"value": "--timezone", "takes_value": True, "description": "IANA timezone"},
                        ],
                        "arguments": [{"value": "--", "description": "Start of command to schedule"}],
                    },
                    "pause": {
                        "description": "Pause a schedule",
                        "arguments": [{"value": "<schedule-id>", "hint_only": True, "description": "Schedule id"}],
                    },
                    "resume": {
                        "description": "Resume a schedule",
                        "arguments": [{"value": "<schedule-id>", "hint_only": True, "description": "Schedule id"}],
                    },
                    "delete": {
                        "description": "Delete a schedule",
                        "arguments": [{"value": "<schedule-id>", "hint_only": True, "description": "Schedule id"}],
                    },
                    "run": {
                        "description": "Fire a schedule now",
                        "arguments": [{"value": "<schedule-id>", "hint_only": True, "description": "Schedule id"}],
                    },
                    "info": {
                        "description": "Show schedule details",
                        "arguments": [{"value": "<schedule-id>", "hint_only": True, "description": "Schedule id"}],
                    },
                }
            },
        },
        {
            "root": "watch",
            "description": "built-in: manage change-detection watchers",
            "autocomplete": {
                "subcommands": {
                    "list": {"description": "List current-session watchers", "closes": True},
                    "create": {
                        "description": "Create a watcher from a completed baseline run",
                        "arguments": [
                            {"value": "<baseline-run-id>", "hint_only": True, "description": "Completed baseline run id"}
                        ],
                        "flags": [
                            {
                                "value": "--cron",
                                "takes_value": True,
                                "description": "Five-field cron expression",
                                "suggest": [
                                    {"value": "0 * * * *", "description": "Every hour"},
                                    {"value": "0 0 * * *", "description": "Every day"},
                                    {"value": "0 0 * * 0", "description": "Every week"},
                                ],
                            },
                            {
                                "value": "--every",
                                "takes_value": True,
                                "description": "Cadence preset",
                                "suggest": [
                                    {"value": "hourly", "description": "Every hour"},
                                    {"value": "daily", "description": "Every day"},
                                    {"value": "weekly", "description": "Every week"},
                                ],
                            },
                            {"value": "--label", "takes_value": True, "description": "Display label"},
                            {"value": "--timezone", "takes_value": True, "description": "IANA timezone"},
                        ],
                    },
                    "pause": {
                        "description": "Pause a watcher",
                        "arguments": [{"value": "<watcher-id>", "hint_only": True, "description": "Watcher id"}],
                    },
                    "resume": {
                        "description": "Resume a watcher",
                        "arguments": [{"value": "<watcher-id>", "hint_only": True, "description": "Watcher id"}],
                    },
                    "delete": {
                        "description": "Delete a watcher",
                        "arguments": [{"value": "<watcher-id>", "hint_only": True, "description": "Watcher id"}],
                    },
                    "accept": {
                        "description": "Accept the latest watcher run as the baseline",
                        "arguments": [{"value": "<watcher-id>", "hint_only": True, "description": "Watcher id"}],
                    },
                    "run": {
                        "description": "Fire a watcher now",
                        "arguments": [{"value": "<watcher-id>", "hint_only": True, "description": "Watcher id"}],
                    },
                    "info": {
                        "description": "Show watcher details",
                        "arguments": [{"value": "<watcher-id>", "hint_only": True, "description": "Watcher id"}],
                    },
                }
            },
        },
        {
            "root": "providers",
            "description": "built-in: show app-native intel provider setup status",
            "autocomplete": {"closes": True},
        },
        {
            "root": "secret",
            "description": "built-in: manage encrypted session secrets",
            "autocomplete": {
                "subcommands": [
                    {
                        "value": "set",
                        "description": "Store or replace an encrypted secret through the browser prompt",
                        "takes_value": True,
                        "insert": "set ",
                        "value_hint": {"value": "<NAME>", "hint_only": True, "description": "Environment-style secret name"},
                    },
                    {"value": "list", "description": "List stored secret names without values", "closes": True},
                    {
                        "value": "unset",
                        "description": "Remove a stored secret",
                        "takes_value": True,
                        "insert": "unset ",
                        "value_hint": {"value": "<NAME>", "hint_only": True, "description": "Environment-style secret name"},
                    },
                    {"value": "show-consumers", "description": "Show app-native intel provider setup status", "closes": True},
                ]
            },
        },
        {
            "root": "session-token",
            "description": "built-in: show or manage persistent session tokens",
            "autocomplete": {
                "subcommands": [
                    {
                        "value": "generate",
                        "description": "Generate a new session token and save it to this browser",
                        "closes": True,
                    },
                    {
                        "value": "set",
                        "description": "Activate an existing session token from another device",
                        "takes_value": True,
                        "insert": "set ",
                        "value_hint": {
                            "value": "<token>",
                            "hint_only": True,
                            "description": "Paste a tok_... token or UUID from another device",
                        },
                    },
                    {"value": "copy", "description": "Copy the active session token to the clipboard", "closes": True},
                    {"value": "clear", "description": "Confirm before removing the active session token", "closes": True},
                    {"value": "rotate", "description": "Generate a new token and migrate all history to it", "closes": True},
                    {"value": "list", "description": "Show the active session token and its creation date", "closes": True},
                    {
                        "value": "revoke",
                        "description": "Permanently invalidate a tok_ token on this server",
                        "takes_value": True,
                        "insert": "revoke ",
                        "value_hint": {
                            "value": "<token>",
                            "hint_only": True,
                            "description": "tok_ token to permanently invalidate on the server",
                        },
                    },
                ]
            },
        },
        {"root": "shortcuts", "description": "built-in: show current keyboard shortcuts", "autocomplete": {"arguments": []}},
        {
            "root": "stats",
            "description": "built-in: show session activity totals and command breakdowns",
            "autocomplete": {"arguments": []},
        },
        {
            "root": "team",
            "description": "built-in: create, join, inspect, and manage teams",
            "autocomplete": {
                "subcommands": [
                    {"value": "status", "description": "Show active personal/team scope", "closes": True},
                    {"value": "list", "description": "List teams joined by the current token", "closes": True},
                    {
                        "value": "create",
                        "description": "Create a team",
                        "takes_value": True,
                        "insert": "create ",
                        "value_hint": {"value": "<name>", "hint_only": True, "description": "Team name"},
                    },
                    {
                        "value": "members",
                        "description": "List members for the active team or supplied team id",
                        "takes_value": True,
                        "insert": "members ",
                        "value_hint": {"value": "<team-id>", "hint_only": True, "description": "Optional team id"},
                    },
                    {
                        "value": "invite",
                        "description": "Create or revoke team invites",
                        "takes_value": True,
                        "insert": "invite ",
                        "value_hint": {"value": "create --role operator", "hint_only": True, "description": "Invite action"},
                    },
                    {
                        "value": "join",
                        "description": "Join a team with an invite code",
                        "takes_value": True,
                        "insert": "join ",
                        "value_hint": {"value": "<invite-code>", "hint_only": True, "description": "Invite code"},
                    },
                    {
                        "value": "leave",
                        "description": "Leave the active team or supplied team id",
                        "takes_value": True,
                        "insert": "leave ",
                        "value_hint": {"value": "<team-id>", "hint_only": True, "description": "Optional team id"},
                    },
                    {
                        "value": "recovery",
                        "description": "Rotate a team recovery code",
                        "takes_value": True,
                        "insert": "recovery rotate",
                    },
                    {"value": "switch", "description": "Show team scope switching guidance", "closes": True},
                ]
            },
        },
        {
            "root": "sort",
            "description": "built-in: sort a session file",
            "feature_required": "workspace",
            "autocomplete": {
                "flags": [
                    {"value": "-r", "description": "Reverse sort"},
                    {"value": "-n", "description": "Numeric sort"},
                    {"value": "-u", "description": "Unique lines"},
                ],
                "argument_limit": 1,
                "arguments": [],
            },
        },
        {
            "root": "status",
            "description": "built-in: show the current session summary, limits, and backend health",
            "autocomplete": {"arguments": []},
        },
        {
            "root": "tail",
            "description": "built-in: print the last lines of a session file",
            "feature_required": "workspace",
            "autocomplete": {
                "flags": [
                    {
                        "value": "-n",
                        "description": "Line count",
                        "takes_value": True,
                        "suggest": [{"value": "10", "description": "Ten lines"}],
                    }
                ],
                "argument_limit": 1,
                "arguments": [],
            },
        },
        {
            "root": "theme",
            "description": "built-in: show or apply the active shell theme",
            "autocomplete": {
                "subcommands": [
                    {"value": "list", "description": "Show available themes", "closes": True},
                    {"value": "current", "description": "Show the active theme", "closes": True},
                    {"value": "set", "description": "Apply a theme", "takes_value": True, "insert": "set "},
                ]
            },
        },
        {
            "root": "tour",
            "description": "built-in: print the onboarding tour inside the terminal",
            "feature_required": "tour",
            "autocomplete": {"subcommands": [{"value": "help", "description": "Show tour command usage", "closes": True}]},
        },
        {"root": "tty", "description": "built-in: show the web terminal device path", "autocomplete": {"arguments": []}},
        {
            "root": "type",
            "description": "built-in: describe whether a command is built-in, installed, or missing",
            "autocomplete": {"argument_limit": 1, "arguments": []},
        },
        {
            "root": "uname",
            "description": "built-in: show the shell platform string",
            "autocomplete": {"flags": [{"value": "-a", "description": "All system information"}]},
        },
        {"root": "uptime", "description": "built-in: show app uptime since process start", "autocomplete": {"arguments": []}},
        {
            "root": "uniq",
            "description": "built-in: collapse adjacent duplicate lines in a session file",
            "feature_required": "workspace",
            "autocomplete": {
                "flags": [{"value": "-c", "description": "Prefix lines by duplicate count"}],
                "argument_limit": 1,
                "arguments": [],
            },
        },
        {
            "root": "var",
            "description": "built-in: set, list, or unset session command variables",
            "autocomplete": {
                "close_after": {"list": 0, "set": 2, "unset": 1},
                "subcommands": [
                    {"value": "list", "description": "Show session variables", "closes": True},
                    {"value": "set", "description": "Set a session variable", "takes_value": True, "insert": "set "},
                    {"value": "unset", "description": "Remove a session variable", "takes_value": True, "insert": "unset "},
                ],
            },
        },
        {
            "root": "version",
            "description": "built-in: show shell, app, Flask, and Python version details",
            "autocomplete": {"arguments": []},
        },
        {
            "root": "which",
            "description": "built-in: locate a built-in command or allowed runtime command",
            "autocomplete": {"argument_limit": 1, "arguments": []},
        },
        {
            "root": "wordlist",
            "description": "built-in: list and search installed SecLists wordlists",
            "autocomplete": {
                "subcommands": [
                    {
                        "value": "list",
                        "description": "List curated wordlists",
                        "takes_value": True,
                        "insert": "list ",
                        "value_hint": {"value": "<category>", "hint_only": True, "description": "Wordlist category"},
                    },
                    {
                        "value": "search",
                        "description": "Search curated wordlists",
                        "takes_value": True,
                        "insert": "search ",
                        "value_hint": {"value": "<term>", "hint_only": True, "description": "Search term"},
                    },
                    {
                        "value": "path",
                        "description": "Print one wordlist path",
                        "takes_value": True,
                        "insert": "path ",
                        "value_hint": {"value": "<name>", "hint_only": True, "description": "Wordlist name or relative path"},
                    },
                ],
                "flags": [{"value": "--all", "description": "List every installed SecLists file"}],
            },
        },
        {
            "root": "workflow",
            "description": "built-in: list, inspect, and run guided workflows",
            "autocomplete": {
                "subcommands": [
                    {"value": "list", "description": "List workflows", "closes": True},
                    {
                        "value": "show",
                        "description": "Show workflow steps",
                        "takes_value": True,
                        "insert": "show ",
                        "value_hint": {"value": "<workflow>", "hint_only": True, "description": "Workflow name"},
                    },
                    {
                        "value": "run",
                        "description": "Run a workflow",
                        "takes_value": True,
                        "insert": "run ",
                        "value_hint": {"value": "<workflow>", "hint_only": True, "description": "Workflow name"},
                    },
                ]
            },
        },
        {"root": "who", "description": "built-in: show the current shell user and session", "autocomplete": {"arguments": []}},
        {
            "root": "whoami",
            "description": "built-in: describe this shell and link to the project README",
            "autocomplete": {"arguments": []},
        },
        {
            "root": "wc",
            "description": "built-in: count lines in a session file",
            "feature_required": "workspace",
            "autocomplete": {
                "flags": [
                    {
                        "value": "-l",
                        "description": "Count lines",
                        "takes_value": True,
                        "value_hint": {"value": "<file>", "hint_only": True, "description": "Session file"},
                    }
                ]
            },
        },
    ],
}
