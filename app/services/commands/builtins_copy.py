# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared display copy for app-native helper commands."""

from __future__ import annotations


# Per-OS key labels use {"mac": ..., "other": ...}. Both sides bind to the same
# DOM event (Option/Alt share e.altKey); only the printed glyph differs.
_CURRENT_SHORTCUTS = [
    (
        "Terminal",
        [
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
        ],
    ),
    (
        "Tabs",
        [
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
        ],
    ),
    (
        "UI",
        [
            ({"mac": "Option+\\", "other": "Alt+\\"}, "toggle the desktop sidebar (rail) open / collapsed"),
            ({"mac": "Option+A", "other": "Alt+A"}, "open or close the Atlas"),
            ({"mac": "Option+Q", "other": "Alt+Q"}, "open Atlas Quick Lookup"),
            ({"mac": "Option+C", "other": "Alt+C"}, "open or close the command registry"),
            ({"mac": "Option+P", "other": "Alt+P"}, "open or close the Projects modal"),
            ({"mac": "Option+M", "other": "Alt+M"}, "open or close the Status Monitor"),
            ({"mac": "Option+S", "other": "Alt+S"}, "toggle the transcript search bar"),
            ({"mac": "Option+Shift+S", "other": "Alt+Shift+S"}, "open or close the Schedules modal"),
            ({"mac": "Option+Shift+W", "other": "Alt+Shift+W"}, "open or close the Watchers modal"),
            ({"mac": "Option+H", "other": "Alt+H"}, "toggle the history drawer"),
            ({"mac": "Option+Shift+F", "other": "Alt+Shift+F"}, "open the Files modal"),
            ({"mac": "Option+,", "other": "Alt+,"}, "open the options panel"),
            ({"mac": "Option+Shift+T", "other": "Alt+Shift+T"}, "open the theme selector"),
            ({"mac": "Option+G", "other": "Alt+G"}, "open the guided workflows panel"),
            ({"mac": "Option+/", "other": "Alt+/"}, "open the FAQ overlay"),
        ],
    ),
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
