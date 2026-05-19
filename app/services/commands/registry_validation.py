"""Low-level command validation helpers for the command registry."""

import re
import shlex
import shutil

NMAP_DENIED_RAW_FLAGS = {"-sS"}
NMAP_SCAN_MODE_FLAGS = {
    "-sA", "-sF", "-sI", "-sL", "-sM", "-sN", "-sO", "-sS",
    "-sT", "-sU", "-sW", "-sX", "-sY", "-sZ", "-sn",
}

# Shell metacharacters that can chain or redirect commands.
# Used for detection (SHELL_CHAIN_RE.search) and splitting (split_chained_commands).
# Both use >>? so > and >> are matched without allowing whitespace between them.
SHELL_CHAIN_RE = re.compile(r'&&|\|\|?|;;?|`|\$\(|>>?|<')

# Pre-compiled path blocking patterns — negative lookbehind prevents false
# positives on URLs such as https://darklab.sh/data/ or /tmp/ path segments.
PATH_DATA_RE = re.compile(r'(?<![\w:/])/data\b')
PATH_TMP_RE = re.compile(r'(?<![\w:/])/tmp\b')

# Loopback address detection — catches bare hostnames and addresses embedded in
# URLs (e.g. "curl http://localhost:8888/diag" or "curl 127.0.0.1:8888/faq").
# Word-boundary anchors prevent false positives on hostnames that contain these
# strings as a substring.
LOOPBACK_RE = re.compile(r'\blocalhost\b|127\.0\.0\.1|\b0\.0\.0\.0\b|\[::1\]', re.IGNORECASE)


def split_command_argv(command: str) -> list[str]:
    """Split a shell-like command string into argv tokens for simple root-command inspection."""
    # Validation works on argv-style tokens only. The app never invokes a shell
    # parser here because that would blur the security model.
    try:
        return shlex.split(command)
    except ValueError:
        return command.strip().split()


def command_root(command: str) -> str | None:
    """Return the first argv token from a command string, lowercased."""
    parts = split_command_argv(command)
    if not parts:
        return None
    return parts[0].strip().lower() or None


def nmap_scan_mode_from_token(token: str) -> str | None:
    for flag in NMAP_SCAN_MODE_FLAGS:
        if token == flag or token.startswith(f"{flag}="):
            return flag
        if token.startswith(flag) and token.startswith("-s") and len(token) > len(flag):
            return flag
    return None


def nmap_raw_scan_restriction_reason(command: str) -> str:
    tokens = split_command_argv(command)
    if not tokens or tokens[0].lower() != "nmap":
        return ""
    if "--privileged" in tokens:
        return "nmap raw-socket mode is not supported; use TCP connect scans with -sT."
    for token in tokens[1:]:
        if nmap_scan_mode_from_token(token) in NMAP_DENIED_RAW_FLAGS:
            return "nmap SYN scans (-sS) are not supported; use TCP connect scans with -sT."
    return ""


def resolve_runtime_command(command_name: str) -> str | None:
    """Return the absolute path to command_name if installed on this instance."""
    return shutil.which(command_name)


def runtime_missing_command_name(command: str) -> str | None:
    """Return the missing root command name for a command string, or None if installed/empty."""
    tokens = split_command_argv(command)
    root = tokens[0].strip().lower() if tokens else None
    if root == "env":
        for token in tokens[1:]:
            if "=" in token and not token.startswith("-"):
                continue
            root = token.strip().lower()
            break
        else:
            root = None
    if not root:
        return None
    return None if resolve_runtime_command(root) else root


def runtime_missing_command_message(command_name: str) -> str:
    """Return the standard instance-level message for missing runtime commands."""
    return f"Command is not installed on this instance: {command_name}"


def split_chained_commands(command: str) -> list[str]:
    """Split a command string on shell chaining, piping, and redirection operators."""
    parts = SHELL_CHAIN_RE.split(command)
    return [p.strip() for p in parts if p.strip()]


def _tokens_start_with(command_tokens: list[str], prefix_tokens: list[str]) -> bool:
    if len(command_tokens) < len(prefix_tokens):
        return False
    return all(cmd.lower() == prefix.lower() for cmd, prefix in zip(command_tokens, prefix_tokens))


def _flag_matches_token(flag: str, token: str) -> bool:
    if not flag:
        return False
    if flag.startswith("--"):
        return token == flag or token.startswith(f"{flag}=")
    if len(flag) == 2 and flag[0] == '-' and flag[1].isalpha():
        if token == flag:
            return True
        # Combined short-flag group matching: `-ve` matches `-e`.
        # Only applies when the token looks like a POSIX short-flag bundle:
        # single dash, all-lowercase alphabetic, at most 4 chars (e.g. -ef, -zvn).
        # Mixed-case tokens such as ProjectDiscovery's -oD or nmap's -sV are
        # long-form/specialized single-dash options and must match exactly.
        if (token.startswith('-') and not token.startswith('--')
                and len(token) <= 4 and token[1:].isalpha() and token[1:].islower()):
            return flag[1] in token[1:]
        return False
    return token == flag


def _grouped_short_flag_members(token: str, allow_grouping_flags: set[str]) -> set[str] | None:
    if not token.startswith("-") or token.startswith("--") or len(token) < 2:
        return None
    if not token[1:].isalpha() or not token[1:].islower():
        return None
    members = {f"-{char}" for char in token[1:]}
    if not members or not members.issubset(allow_grouping_flags):
        return None
    return members


def _allowed_prefix_matches_with_grouping(
    command_tokens: list[str],
    prefix_tokens: list[str],
    allow_grouping_flags: set[str],
) -> bool:
    if not command_tokens or not prefix_tokens or not allow_grouping_flags:
        return False
    if command_tokens[0].lower() != prefix_tokens[0].lower():
        return False

    required_grouped_flags = set()
    for token in prefix_tokens[1:]:
        if token in allow_grouping_flags:
            required_grouped_flags.add(token)
            continue
        members = _grouped_short_flag_members(token, allow_grouping_flags)
        if members:
            required_grouped_flags.update(members)
            continue
        # Keep non-groupable prefixes on the original exact-prefix path.
        return False
    if not required_grouped_flags:
        return False

    command_grouped_flags = set()
    for token in command_tokens[1:]:
        members = _grouped_short_flag_members(token, allow_grouping_flags)
        if members:
            command_grouped_flags.update(members)

    return required_grouped_flags.issubset(command_grouped_flags)


def is_allowed_by_policy(command_tokens: list[str], allowed: list[str], allow_grouping: dict[str, set[str]]) -> bool:
    cmd_lower = shlex.join(command_tokens).lower()
    for prefix in allowed:
        if cmd_lower == prefix or cmd_lower.startswith(prefix + " "):
            return True
        prefix_tokens = split_command_argv(prefix)
        root = prefix_tokens[0].lower() if prefix_tokens else ""
        if _allowed_prefix_matches_with_grouping(command_tokens, prefix_tokens, allow_grouping.get(root, set())):
            return True
    return False


def _nmap_output_deny_matches(flag: str, token: str) -> bool:
    if flag != "-o":
        return False
    return any(
        token == output_flag or token.startswith(output_flag)
        for output_flag in ("-oN", "-oX", "-oG", "-oA", "-oS")
    )


def _is_exempted_nmap_output_token(token: str, exempt_flags: set[str]) -> bool:
    return any(
        exempt_flag in {"-oN", "-oX", "-oG", "-oA", "-oS"}
        and (token == exempt_flag or token.startswith(exempt_flag))
        for exempt_flag in exempt_flags
    )


def is_denied(command: str, deny_entries: list[str], *, exempt_flags: set[str] | None = None) -> bool:
    """Return True if command matches any deny entry."""
    command_tokens = split_command_argv(command)
    if not command_tokens:
        return False

    exempt_flags = exempt_flags or set()
    for d in deny_entries:
        deny_tokens = split_command_argv(d)
        if not deny_tokens:
            continue

        if len(deny_tokens) == 1:
            if command_tokens[0].lower() == deny_tokens[0].lower():
                return True
            continue

        tool_prefix = deny_tokens[:-1]
        flag = deny_tokens[-1]
        if flag in exempt_flags:
            continue
        if not _tokens_start_with(command_tokens, tool_prefix):
            continue

        tail = command_tokens[len(tool_prefix):]
        for idx, token in enumerate(tail):
            if not (
                _flag_matches_token(flag, token)
                or (command_tokens[0].lower() == "nmap" and _nmap_output_deny_matches(flag, token))
            ):
                continue
            if flag == "-o" and command_tokens[0].lower() == "nmap" and _is_exempted_nmap_output_token(token, exempt_flags):
                continue
            if idx + 1 < len(tail) and tail[idx + 1] == "/dev/null":
                break
            return True
    return False
