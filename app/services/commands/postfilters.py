"""Synthetic post-filter pipeline parsing for app-native pipe helpers."""

from __future__ import annotations

import shlex


def _split_shell_control_tokens(command: str) -> list[str]:
    """Split a shell-like command while keeping control operators as tokens."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars='|&;<>')
        lexer.whitespace_split = True
        lexer.commenters = ''
        return list(lexer)
    except ValueError:
        return []


def _parse_synthetic_grep_stage(stage_tokens: list[str]) -> tuple[dict | None, str | None]:
    """Parse the post-filter stage for the narrow app-native grep helper."""
    if stage_tokens[0].lower() != 'grep':
        return None, None

    options = {"ignore_case": False, "invert_match": False, "extended": False}
    pattern = None
    for token in stage_tokens[1:]:
        if pattern is not None:
            return None, "Synthetic grep only supports a single pattern argument."
        if token.startswith('-') and token != '-':
            if token.startswith('--'):
                return None, "Synthetic grep supports only -i, -v, and -E."
            for flag in token[1:]:
                if flag == 'i':
                    options["ignore_case"] = True
                elif flag == 'v':
                    options["invert_match"] = True
                elif flag == 'E':
                    options["extended"] = True
                else:
                    return None, "Synthetic grep supports only -i, -v, and -E."
            continue
        pattern = token

    if pattern is None:
        return None, "Synthetic grep requires a pattern."

    return {
        "kind": "grep",
        "pattern": pattern,
        **options,
    }, None


def _parse_synthetic_head_tail_stage(stage_tokens: list[str]) -> tuple[dict | None, str | None]:
    """Parse narrow app-native head/tail helpers with default count, -n, or -<number>."""
    command_name = stage_tokens[0].lower()
    if command_name not in {"head", "tail"}:
        return None, None

    count = 10
    if len(stage_tokens) == 1:
        return {"kind": command_name, "count": count}, None

    if len(stage_tokens) == 2 and stage_tokens[1].startswith('-') and stage_tokens[1][1:].isdigit():
        return {"kind": command_name, "count": int(stage_tokens[1][1:])}, None

    if len(stage_tokens) != 3 or stage_tokens[1] != "-n":
        return None, f"Synthetic {command_name} supports only `-n <count>` or `-<count>`."
    if not stage_tokens[2].isdigit():
        return None, f"Synthetic {command_name} requires a non-negative numeric count."

    return {"kind": command_name, "count": int(stage_tokens[2])}, None


def _parse_synthetic_wc_stage(stage_tokens: list[str]) -> tuple[dict | None, str | None]:
    """Parse the narrow app-native `wc -l` helper."""
    if stage_tokens[0].lower() != "wc":
        return None, None
    if stage_tokens[1:] == ["-l"]:
        return {"kind": "wc_l"}, None
    return None, "Synthetic wc supports only `wc -l`."


_SORT_VALID_FLAGS = frozenset("rnu")


def _parse_synthetic_sort_stage(stage_tokens: list[str]) -> tuple[dict | None, str | None]:
    """Parse the narrow app-native sort helper. Supports -r, -n, -u in any combination."""
    if stage_tokens[0].lower() != "sort":
        return None, None
    if len(stage_tokens) == 1:
        return {"kind": "sort", "reverse": False, "numeric": False, "unique": False}, None
    if len(stage_tokens) == 2:
        flag = stage_tokens[1]
        if flag.startswith('-') and flag[1:] and set(flag[1:]).issubset(_SORT_VALID_FLAGS):
            chars = set(flag[1:])
            return {"kind": "sort", "reverse": "r" in chars,
                    "numeric": "n" in chars, "unique": "u" in chars}, None
    return None, "Synthetic sort supports only -r, -n, and -u flags."


def _parse_synthetic_uniq_stage(stage_tokens: list[str]) -> tuple[dict | None, str | None]:
    """Parse the narrow app-native uniq helper. Supports uniq and uniq -c."""
    if stage_tokens[0].lower() != "uniq":
        return None, None
    if len(stage_tokens) == 1:
        return {"kind": "uniq", "count": False}, None
    if len(stage_tokens) == 2 and stage_tokens[1] == "-c":
        return {"kind": "uniq", "count": True}, None
    return None, "Synthetic uniq supports only -c."


def _parse_synthetic_postfilter_stage(stage_tokens: list[str]) -> tuple[dict | None, str | None]:
    for parser in (
        _parse_synthetic_grep_stage,
        _parse_synthetic_head_tail_stage,
        _parse_synthetic_wc_stage,
        _parse_synthetic_sort_stage,
        _parse_synthetic_uniq_stage,
    ):
        spec, error = parser(stage_tokens)
        if spec or error:
            return spec, error
    return None, None


def parse_synthetic_postfilter(command: str) -> tuple[dict | None, str | None]:
    """Parse a narrow app-native `command | helper ...` post-filter pipeline.

    Returns (spec, error_message). spec is None when the command does not use
    the synthetic post-filter path. error_message is populated only when the
    input is clearly trying to use a supported helper but the stage is invalid.
    """
    stripped = command.strip()
    if '|' not in stripped:
        return None, None
    if '`' in stripped or '$(' in stripped:
        return None, None

    tokens = _split_shell_control_tokens(stripped)
    if not tokens:
        return None, None

    disallowed_control = {'&&', '||', ';', ';;', '>', '>>', '<', '&'}
    if any(token in disallowed_control for token in tokens):
        return None, None

    pipe_indexes = [index for index, token in enumerate(tokens) if token == '|']
    if not pipe_indexes:
        return None, None

    base_tokens = tokens[:pipe_indexes[0]]
    if not base_tokens:
        return None, "Synthetic post-filters require `command | helper ...`."

    stage_specs: list[dict] = []
    stage_start = pipe_indexes[0] + 1
    for pipe_index in pipe_indexes[1:] + [len(tokens)]:
        stage_tokens = tokens[stage_start:pipe_index]
        if not stage_tokens:
            return None, "Synthetic post-filters require `command | helper ...`."

        spec, error = _parse_synthetic_postfilter_stage(stage_tokens)
        if error:
            return None, error
        if not spec:
            return None, None

        stage_specs.append(spec)
        stage_start = pipe_index + 1

    return {
        "base_command": shlex.join(base_tokens),
        "stages": stage_specs,
        "kind": stage_specs[0]["kind"],
    }, None
