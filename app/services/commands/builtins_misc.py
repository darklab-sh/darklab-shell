"""Miscellaneous and guardrail-flavored built-in command handlers."""

from __future__ import annotations

import random

from config import CFG
from services.commands.builtins_catalog import (
    _SNARKY_POWEROFF_RESPONSES,
    _SNARKY_REBOOT_RESPONSES,
    _SNARKY_RM_ROOT_RESPONSES,
    _SNARKY_SU_RESPONSES,
    _SNARKY_SUDO_RESPONSES,
    _SNARKY_SUDO_TARGET_RESPONSES,
)
from services.commands.builtins_format import text_lines as _text_lines
from services.commands.registry import load_ascii_art, split_command_argv


def run_builtin_banner(load_ascii_art_func=load_ascii_art) -> list[dict[str, object]]:
    art = load_ascii_art_func()
    if not art:
        return [{"type": "output", "text": CFG["app_name"]}]
    return _text_lines(art.splitlines())


def run_builtin_clear() -> list[dict[str, object]]:
    return [{"type": "clear"}]


def run_builtin_fortune() -> list[dict[str, object]]:
    fortunes = [
        "Trust the output, not the hunch.",
        "A green terminal does not make the command a good idea.",
        "The most expensive typo is the one you run twice.",
        "Confidence is not a transport protocol.",
        "A quiet port is still answering a question.",
        "Somewhere, a forgotten TXT record knows the truth.",
        "A single open port can ruin an otherwise peaceful afternoon.",
        "You are one flag away from either clarity or folklore.",
        "There is no problem so small that a bigger scan cannot misunderstand it.",
        "A teapot would at least return 418 honestly.",
        "Beware the host that answers quickly and says nothing useful.",
        "Documentation is just cached incident response.",
        "The shell is calm. The operator is optional.",
        "The answer may be in the PTR record, waiting like a cryptic side quest.",
        "Never trust a service that calls itself 'temporary' in production.",
        "The sixth retry is where superstition starts dressing like methodology.",
        "Some DNS zones are less configuration and more oral tradition.",
        "If the port is closed, at least it had the decency to be clear.",
        "A 200 response can still be deeply judgmental.",
        "A staging subdomain is just production wearing sunglasses.",
        "Half of web security is noticing what should have been boring.",
        "Every infrastructure story eventually features DNS, TLS, or someone named Chris.",
        "A config drift chart is just a weather report for future incidents.",
        "There is no artifact more permanent than a temporary override.",
        "Some outages are resolved by code. Others are resolved by finding the right YAML.",
        "The incident bridge is where certainty goes to become collaborative.",
        "A feature flag left on for six months is just architecture now.",
    ]
    return [{"type": "output", "text": random.choice(fortunes)}]


def run_builtin_groups() -> list[dict[str, object]]:
    return [{"type": "output", "text": f"{CFG['app_name']} operators"}]


def run_builtin_poweroff() -> list[dict[str, object]]:
    return [{"type": "output", "text": random.choice(_SNARKY_POWEROFF_RESPONSES)}]


def run_builtin_reboot() -> list[dict[str, object]]:
    return [{"type": "output", "text": random.choice(_SNARKY_REBOOT_RESPONSES)}]


def run_builtin_rm_root() -> list[dict[str, object]]:
    return [{"type": "output", "text": random.choice(_SNARKY_RM_ROOT_RESPONSES)}]


def run_builtin_sudo(command: str) -> list[dict[str, object]]:
    parts = split_command_argv(command)
    if len(parts) == 1:
        return [{"type": "output", "text": random.choice(_SNARKY_SUDO_RESPONSES)}]
    target = " ".join(parts[1:])
    template = random.choice(_SNARKY_SUDO_TARGET_RESPONSES)
    return [{"type": "output", "text": template.format(target=target)}]


def run_builtin_su(command: str) -> list[dict[str, object]]:
    prefix = "sudo" if command.strip().lower().startswith("sudo") else "su"
    text = random.choice(_SNARKY_SU_RESPONSES).replace("su:", f"{prefix}:")
    return [{"type": "output", "text": text}]


def run_builtin_xyzzy() -> list[dict[str, object]]:
    return [{"type": "output", "text": "Nothing happens."}]


def run_builtin_coffee() -> list[dict[str, object]]:
    return _text_lines([
        "HTTP/1.1 418 I'm a teapot",
        "Content-Type: text/plain",
        "",
        "Brewing coffee with a teapot is unsupported.",
    ])


def run_builtin_fork_bomb() -> list[dict[str, object]]:
    return _text_lines([
        "bash: fork bomb politely declined",
        "system remains operational",
    ])
