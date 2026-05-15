"""
Static catalog data for app-native built-in commands.
"""

from __future__ import annotations

import re


# Per-OS key labels use {"mac": ..., "other": ...}. Both sides bind to the same
# DOM event (Option/Alt share e.altKey); only the printed glyph differs.
_CURRENT_SHORTCUTS = [
    ("Terminal", [
        ("?", "open the keyboard shortcuts overlay (works from the prompt when empty)"),
        ("Ctrl+C", "running => open kill confirm; idle => fresh prompt line"),
        ("Up / Down on blank prompt", "cycle recent command history"),
        (
            "Ctrl+R",
            "reverse-i-search history; Up/Down/Ctrl+R cycle; Enter runs; Tab accepts; Escape restores draft",
        ),
        ("Ctrl+W", "delete one word to the left"),
        ("Ctrl+U", "delete to the beginning of the line"),
        ("Ctrl+A", "move to the beginning of the line"),
        ("Ctrl+K", "delete to the end of the line"),
        ("Ctrl+E", "move to the end of the line"),
        ({"mac": "Option+B / Option+F", "other": "Alt+B / Alt+F"}, "move backward / forward by word"),
        (
            {"mac": "Option+Left / Option+Right", "other": "Alt+Left / Alt+Right"},
            "move backward / forward by word",
        ),
        ("Ctrl+L", "clear the active tab"),
        ("Ctrl+D", "close the current tab"),
    ]),
    ("Tabs", [
        ({"mac": "Option+T", "other": "Alt+T"}, "open a new tab"),
        ({"mac": "Option+W", "other": "Alt+W"}, "close the current tab"),
        (
            {"mac": "Shift+Option+Left / Shift+Option+Right", "other": "Shift+Alt+Left / Shift+Alt+Right"},
            "switch to previous / next tab",
        ),
        ({"mac": "Option+Tab", "other": "Alt+Tab"}, "cycle to next tab (add Shift to reverse)"),
        ({"mac": "Option+1 … Option+9", "other": "Alt+1 … Alt+9"}, "jump directly to tab 1 … 9"),
        ({"mac": "Option+Shift+P", "other": "Alt+Shift+P"}, "create a permalink for the active tab"),
        ({"mac": "Option+Shift+C", "other": "Alt+Shift+C"}, "copy active-tab output"),
    ]),
    ("UI", [
        ({"mac": "Option+\\", "other": "Alt+\\"}, "toggle the desktop sidebar (rail) open / collapsed"),
        ({"mac": "Option+C", "other": "Alt+C"}, "open or close the command registry"),
        ({"mac": "Option+P", "other": "Alt+P"}, "open or close the Projects modal"),
        ({"mac": "Option+M", "other": "Alt+M"}, "open or close the Status Monitor"),
        ({"mac": "Option+S", "other": "Alt+S"}, "toggle the transcript search bar"),
        ({"mac": "Option+H", "other": "Alt+H"}, "toggle the history drawer"),
        ({"mac": "Option+Shift+F", "other": "Alt+Shift+F"}, "open the Files modal"),
        ({"mac": "Option+,", "other": "Alt+,"}, "open the options panel"),
        ({"mac": "Option+Shift+T", "other": "Alt+Shift+T"}, "open the theme selector"),
        ({"mac": "Option+G", "other": "Alt+G"}, "open the guided workflows panel"),
        ({"mac": "Option+/", "other": "Alt+/"}, "open the FAQ overlay"),
    ]),
]
_SNARKY_SUDO_RESPONSES = [
    "sudo: i asked the kernel. the kernel said no.",
    "sudo: root is occupied. please leave a message after the 403.",
    "sudo: this is still a shell, not a coup.",
    "sudo: administrative confidence detected; administrative power not found.",
    "sudo: this shell respects your ambition and ignores it completely.",
    "sudo: the stack has reviewed your request and chosen comedy.",
    "sudo: root privileges are currently in another castle.",
    "sudo: kernel says no, browser says also no.",
    "sudo: privilege escalation blocked at layer 8.",
    "sudo: request denied by the web shell's sense of self-preservation.",
]
_SNARKY_SUDO_TARGET_RESPONSES = [
    "sudo: '{target}' is not listed in the threat model, but still no.",
    "sudo: '{target}' has been forwarded to /dev/null for executive review.",
    "sudo: ran '{target}' through the web shell authorization matrix. verdict: absolutely not.",
    "sudo: '{target}' would require a kernel, a real tty, and a better plan.",
    "sudo: '{target}' has been denied by a bipartisan coalition of guardrails.",
    "sudo: '{target}' would make a great postmortem title.",
    "sudo: '{target}' was intercepted by responsible adults.",
    "sudo: '{target}' has failed the vibe check.",
    "sudo: '{target}' has been denied for the continued health of the infrastructure.",
    "sudo: nice try with '{target}', but no.",
    "sudo: '{target}' was rejected before it could become a plan.",
]
_SNARKY_REBOOT_RESPONSES = [
    "reboot: the uptime counter would like a word.",
    "reboot: that's a 4am pager alert in text form. still no.",
    "reboot: graceful shutdown initiated... just kidding.",
    "reboot: systemd is not listening to you right now.",
    "reboot: denied. the server prefers consciousness.",
    "reboot: if you need closure, may I suggest 'clear'?",
    "reboot: that's one way to hide the evidence, but still no.",
    "reboot: the server is not taking user suggestions for downtime.",
    "reboot: let's not turn a diagnostic console into a blackout.",
]
_SNARKY_POWEROFF_RESPONSES = [
    "poweroff: the uptime counter would like a word.",
    "poweroff: that's a 4am pager alert in text form. still no.",
    "poweroff: graceful power-down initiated... just kidding.",
    "poweroff: systemd is not listening to you right now.",
    "poweroff: denied. the server prefers consciousness.",
    "poweroff: if you need closure, may I suggest 'clear'?",
    "poweroff: that's one way to hide the evidence, but still no.",
    "poweroff: the server is not taking user suggestions for downtime.",
    "poweroff: let's not turn a diagnostic console into a blackout.",
]
_SNARKY_RM_ROOT_RESPONSES = [
    "rm: no filesystem was harmed in the running of this command.",
    "rm: this is a web shell. the / you're reaching for is a container. the container says no.",
    "rm: truly, a classic. still no.",
    "rm: operation blocked by the 'i like having a root filesystem' policy.",
    "rm: you'll have to cause your own outage the old-fashioned way.",
    "rm: the / would like to remain.",
]
_SNARKY_SU_RESPONSES = [
    "su: root login is not available in this shell.",
    "su: this browser tab does not come with a root shell.",
    "su: no tty, no pam, no chance.",
    "su: root remains a management problem for another machine.",
    "su: request denied by the continued health of the infrastructure.",
]
_FORK_BOMB_RE = re.compile(r"^:\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:$")
_SPECIAL_BUILTIN_COMMANDS = {
    ":(){ :|:& };:": "fork_bomb",
    "coffee": "coffee",
    "halt": "poweroff",
    "ip a": "ip_addr",
    "poweroff": "poweroff",
    "rm -fr /": "rm_root",
    "rm -rf /": "rm_root",
    "rm -r -f /": "rm_root",
    "rm -f -r /": "rm_root",
    "shutdown now": "poweroff",
    "sudo -s": "su_shell",
    "sudo su": "su_shell",
    "su": "su_shell",
    "xyzzy": "xyzzy",
}
_DOCUMENTED_BUILTIN_COMMANDS = [
    {"name": "banner", "description": "Print the configured banner art without replaying welcome.", "root": "banner"},
    {"name": "cat <file>", "description": "Show a session file.", "root": "cat"},
    {"name": "cd [folder]", "description": "Change the current workspace folder for this tab.", "root": "cd"},
    {"name": "clear", "description": "Clear the current terminal tab output.", "root": "clear"},
    {"name": "commands", "description": "List built-in and allowed external commands.", "root": "commands"},
    {"name": "config", "description": "Show or update user options from the terminal.", "root": "config"},
    {"name": "date", "description": "Show the current server time.", "root": "date"},
    {"name": "df -h", "description": "Show a compact filesystem summary.", "root": "df"},
    {"name": "env", "description": "Show core environment values for this shell.", "root": "env"},
    {"name": "exit", "description": "Close the current tab.", "root": "exit"},
    {
        "name": "faq",
        "description": "Show configured FAQ entries inside the terminal with question and answer formatting.",
        "root": "faq",
    },
    {"name": "fortune", "description": "Print a short operator-themed one-liner.", "root": "fortune"},
    {"name": "free -h", "description": "Show a compact memory summary.", "root": "free"},
    {"name": "groups", "description": "Show the shell group membership.", "root": "groups"},
    {"name": "grep <search> <file>", "description": "Filter a session file.", "root": "grep"},
    {"name": "head [-n N] <file>", "description": "Show the first lines of a session file.", "root": "head"},
    {"name": "help", "description": "Show guidance for README, FAQ, shortcuts, and command discovery.", "root": "help"},
    {"name": "history", "description": "List command history from this session.", "root": "history"},
    {"name": "hostname", "description": "Show the configured shell instance name.", "root": "hostname"},
    {"name": "id", "description": "Show the shell identity.", "root": "id"},
    {"name": "intel <type> <value>", "description": "Look up passive intel from app-native providers.", "root": "intel"},
    {"name": "ip a", "description": "Show a minimal shell network interface view.", "exact": "ip a"},
    {"name": "jobs", "description": "Alias for `runs`.", "root": "jobs"},
    {"name": "last", "description": "Show recent completed runs with timestamps and exit codes.", "root": "last"},
    {"name": "limits", "description": "Show configured runtime, history, and retention limits.", "root": "limits"},
    {"name": "ll", "description": "Long-list session files.", "root": "ll"},
    {"name": "ls", "description": "List session files.", "root": "ls"},
    {"name": "man <cmd>", "description": "Show the real man page for an allowed command.", "root": "man"},
    {"name": "mkdir <folder>", "description": "Create a session folder.", "root": "mkdir"},
    {"name": "ps", "description": "Show the current shell process view plus recent session commands.", "root": "ps"},
    {"name": "pwd", "description": "Show the session files path.", "root": "pwd"},
    {"name": "project", "description": "Create, select, and link project workspaces from the terminal.", "root": "project"},
    {"name": "providers", "description": "Alias for `secret show-consumers`.", "root": "providers"},
    {"name": "quit", "description": "Alias for `exit`.", "root": "quit"},
    {"name": "retention", "description": "Show retention and persisted-output settings.", "root": "retention"},
    {"name": "mv <source> <destination>", "description": "Move or rename a session file or folder.", "root": "mv"},
    {"name": "rm <file>", "description": "Remove a session file after confirmation.", "root": "rm"},
    {"name": "route", "description": "Show the shell routing table summary.", "root": "route"},
    {"name": "runs [-v|--json]", "description": "Show app-native active run metadata for this session.", "root": "runs"},
    {"name": "secret", "description": "Set, list, and remove encrypted session secrets for API-backed tools.", "root": "secret"},
    {"name": "session-token", "description": "Show session token status.", "root": "session-token"},
    {"name": "shortcuts", "description": "Show current keyboard shortcuts.", "root": "shortcuts"},
    {"name": "stats", "description": "Show session activity totals and command-root breakdowns.", "root": "stats"},
    {"name": "status", "description": "Show the current session summary, limits, and backend health.", "root": "status"},
    {"name": "sort [-r|-n|-u] <file>", "description": "Sort a session file.", "root": "sort"},
    {"name": "tail [-n N] <file>", "description": "Show the last lines of a session file.", "root": "tail"},
    {"name": "theme", "description": "Show or apply the active shell theme from the terminal.", "root": "theme"},
    {"name": "tour", "description": "Print the onboarding tour inside the terminal.", "root": "tour"},
    {"name": "tty", "description": "Show the web terminal device path.", "root": "tty"},
    {"name": "type <cmd>", "description": "Describe whether a command is built in, installed, or missing.", "root": "type"},
    {"name": "uname [-a]", "description": "Show the shell platform string.", "root": "uname"},
    {"name": "uptime", "description": "Show app uptime since process start.", "root": "uptime"},
    {"name": "uniq [-c] <file>", "description": "Collapse adjacent duplicate lines in a session file.", "root": "uniq"},
    {"name": "var", "description": "Set, list, or unset session command variables.", "root": "var"},
    {"name": "version", "description": "Show shell, app, Flask, and Python version details.", "root": "version"},
    {"name": "file", "description": "List, view, create, edit, download, move, or remove session files.", "root": "file"},
    {"name": "which <cmd>", "description": "Locate a built-in command or allowed runtime command.", "root": "which"},
    {"name": "who", "description": "Show the current shell user and session.", "root": "who"},
    {"name": "whoami", "description": "Describe this shell and link to the project README.", "root": "whoami"},
    {"name": "wc -l <file>", "description": "Count lines in a session file.", "root": "wc"},
    {"name": "wordlist", "description": "List and search installed SecLists wordlists.", "root": "wordlist"},
    {"name": "workflow", "description": "List, inspect, and run guided workflows from the terminal.", "root": "workflow"},
]
_BUILTIN_COMMAND_HELP = [(entry["name"], entry["description"]) for entry in _DOCUMENTED_BUILTIN_COMMANDS]
_DOCUMENTED_BUILTIN_COMMAND_ROOTS = {entry["root"] for entry in _DOCUMENTED_BUILTIN_COMMANDS if "root" in entry}
_BUILTIN_COMMANDS = _DOCUMENTED_BUILTIN_COMMAND_ROOTS | {"reboot", "sudo"}
_WORKSPACE_ALIAS_ROOTS = {"cat", "cd", "grep", "head", "ll", "ls", "mkdir", "mv", "rm", "sort", "tail", "uniq", "wc"}
_WORKSPACE_BUILTIN_ROOTS = _WORKSPACE_ALIAS_ROOTS | {"file"}
_SYNTHETIC_MAN_EXCLUDED_ROOTS = {"cat", "ll", "ls", "rm"}
