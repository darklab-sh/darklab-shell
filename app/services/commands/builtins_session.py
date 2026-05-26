"""Session identity and variable built-in command handlers."""

from __future__ import annotations

from services.commands.builtins_format import (
    ansi_dim,
    ansi_green,
    format_native_record,
    output_line,
)
from services.commands.registry import split_command_argv
from services.session.variables import (
    InvalidSessionVariableName,
    InvalidSessionVariableValue,
    list_session_variables,
    normalize_variable_name,
    set_session_variable,
    unset_session_variable,
)


def mask_session_token(token: str) -> str:
    """Return a display-safe masked version of a session token or session UUID."""
    if token.startswith("tok_"):
        return "tok_" + token[4:8] + "••••"
    return token[:8] + "••••••••"


def run_builtin_session_token(cmd: str, session_id: str) -> list[dict[str, object]]:
    parts = split_command_argv(cmd)
    subcommand = parts[1].lower() if len(parts) > 1 else ""

    if subcommand in ("generate", "set", "copy", "clear", "rotate", "list", "revoke"):
        # These subcommands are intercepted and executed client-side; they
        # should never reach the server. Return a safe fallback message.
        return [output_line("session-token: subcommands run client-side — reload the page and try again.")]

    if subcommand:
        return [
            output_line(f"session-token: unknown subcommand '{subcommand}'"),
            output_line("Usage: session-token [generate | copy | set <value> | clear | rotate | list | revoke <token>]"),
        ]

    # Bare session-token shows status from the server-side session_id.
    masked = mask_session_token(session_id)
    width = 14
    if session_id.startswith("tok_"):
        return [
            output_line(format_native_record("session token", masked, width), "builtin-kv"),
            output_line(format_native_record("status", ansi_green("active"), width), "builtin-kv"),
            output_line(format_native_record("storage", "localStorage (session_token)", width), "builtin-kv"),
        ]
    return [
        output_line(format_native_record("session", masked, width), "builtin-kv"),
        output_line(format_native_record("status", ansi_dim("anonymous (no session token set)"), width), "builtin-kv"),
        output_line(
            format_native_record(
                "tip",
                "run 'session-token generate' to create a persistent token",
                width,
            ),
            "builtin-kv",
        ),
    ]


def run_builtin_var(cmd: str, session_id: str) -> list[dict[str, object]]:
    parts = split_command_argv(cmd)
    subcommand = parts[1].lower() if len(parts) > 1 else "list"
    width = 12

    if subcommand in {"help", "-h", "--help"}:
        return [
            output_line("Session command variables:", "builtin-section"),
            output_line("  var set NAME value", "builtin-plain"),
            output_line("  var list", "builtin-plain"),
            output_line("  var unset NAME", "builtin-plain"),
            output_line("Reference variables as $NAME or ${NAME}. Values expand before command validation.", "builtin-note"),
            output_line("Names must match [A-Z][A-Z0-9_]{0,31}. Do not store secrets here.", "builtin-note"),
        ]

    if subcommand == "list":
        variables = list_session_variables(session_id)
        if not variables:
            return [output_line("No session variables set.", "builtin-note")]
        lines = [output_line("Session variables:", "builtin-section")]
        for name, value in variables.items():
            lines.append(output_line(format_native_record(name, value, width), "builtin-kv"))
        return lines

    if subcommand == "set":
        if len(parts) < 4:
            return [
                output_line("Usage: var set NAME value"),
                output_line("Example: var set HOST ip.darklab.sh"),
            ]
        name = parts[2]
        value = " ".join(parts[3:])
        try:
            normalized_name = normalize_variable_name(name)
            set_session_variable(session_id, normalized_name, value)
        except (InvalidSessionVariableName, InvalidSessionVariableValue) as exc:
            return [output_line(f"var: {exc}")]
        return [output_line(f"Set ${normalized_name} = {value}", "builtin-success")]

    if subcommand in {"unset", "delete", "rm"}:
        if len(parts) != 3:
            return [output_line("Usage: var unset NAME")]
        try:
            normalized_name = normalize_variable_name(parts[2])
            removed = unset_session_variable(session_id, normalized_name)
        except InvalidSessionVariableName as exc:
            return [output_line(f"var: {exc}")]
        status = "removed" if removed else "was not set"
        return [output_line(f"${normalized_name} {status}.", "builtin-success" if removed else "builtin-note")]

    return [
        output_line(f"var: unknown subcommand '{subcommand}'"),
        output_line("Usage: var [list] | var set NAME value | var unset NAME"),
    ]
