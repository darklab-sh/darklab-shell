# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Synthetic post-filter pipeline parsing for app-native pipe helpers."""

from __future__ import annotations

import re
import shlex

from services.workspace.models import InvalidWorkspacePath
from services.workspace.paths import validate_relative_path


_FILE_DESCRIPTOR_REDIRECT_RE = re.compile(r'(^|\s)\d+>>?')


def _split_shell_control_tokens(command: str) -> list[str]:
    """Split a shell-like command while keeping control operators as tokens."""
    try:
        lexer = shlex.shlex(command, posix=False, punctuation_chars='|&;<>')
        lexer.whitespace_split = True
        lexer.commenters = ''
        return list(lexer)
    except ValueError:
        return []


def _is_quoted_token(token: str) -> bool:
    return len(token) >= 2 and token[0] in {"'", '"'} and token[-1] == token[0]


def _unquote_token(token: str) -> str:
    return token[1:-1] if _is_quoted_token(token) else token


def _output_sink_path(token: str) -> tuple[str | None, str | None]:
    destination = _unquote_token(token).strip()
    if not destination:
        return None, "Output redirection requires a destination file."
    if destination.endswith('/'):
        return None, "Output redirection destination must be a file, not a directory."
    try:
        validate_relative_path(destination)
    except InvalidWorkspacePath as exc:
        return None, f"Output redirection destination is invalid: {exc}"
    return destination, None


def _parse_synthetic_grep_stage(stage_tokens: list[str]) -> tuple[dict | None, str | None]:
    """Parse the post-filter stage for the narrow app-native grep helper."""
    if _unquote_token(stage_tokens[0]).lower() != 'grep':
        return None, None

    options = {"ignore_case": False, "invert_match": False, "extended": False}
    pattern = None
    index = 1
    while index < len(stage_tokens):
        raw_token = stage_tokens[index]
        token = _unquote_token(raw_token)
        quoted = _is_quoted_token(raw_token)
        if pattern is not None:
            return None, "Synthetic grep only supports a single pattern argument."
        if quoted:
            pattern = token
            index += 1
            continue
        if token == "--":
            if index + 1 >= len(stage_tokens):
                return None, "Synthetic grep requires a pattern."
            pattern = _unquote_token(stage_tokens[index + 1])
            index += 2
            continue
        if token == "-e":
            if index + 1 >= len(stage_tokens):
                return None, "Synthetic grep requires a pattern."
            pattern = _unquote_token(stage_tokens[index + 1])
            index += 2
            continue
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
            index += 1
            continue
        pattern = token
        index += 1

    if pattern is None:
        return None, "Synthetic grep requires a pattern."

    return {
        "kind": "grep",
        "pattern": pattern,
        **options,
    }, None


def _parse_synthetic_head_tail_stage(stage_tokens: list[str]) -> tuple[dict | None, str | None]:
    """Parse narrow app-native head/tail helpers with default count, -n, or -<number>."""
    stage_tokens = [_unquote_token(token) for token in stage_tokens]
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
    stage_tokens = [_unquote_token(token) for token in stage_tokens]
    if stage_tokens[0].lower() != "wc":
        return None, None
    if stage_tokens[1:] == ["-l"]:
        return {"kind": "wc_l"}, None
    return None, "Synthetic wc supports only `wc -l`."


_SORT_VALID_FLAGS = frozenset("rnu")


def _parse_synthetic_sort_stage(stage_tokens: list[str]) -> tuple[dict | None, str | None]:
    """Parse the narrow app-native sort helper. Supports -r, -n, -u in any combination."""
    stage_tokens = [_unquote_token(token) for token in stage_tokens]
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
    stage_tokens = [_unquote_token(token) for token in stage_tokens]
    if stage_tokens[0].lower() != "uniq":
        return None, None
    if len(stage_tokens) == 1:
        return {"kind": "uniq", "count": False}, None
    if len(stage_tokens) == 2 and stage_tokens[1] == "-c":
        return {"kind": "uniq", "count": True}, None
    return None, "Synthetic uniq supports only -c."


def _json_selector_path(value: str) -> list[str]:
    return [part for part in str(value or "").split(".") if part]


def _parse_json_selector_expression(expression: str) -> dict | None:
    text = str(expression or "").strip()
    if not text or len(text) > 160:
        return None
    if re.search(r"[`;{}$\\]", text):
        return None

    has_match = re.fullmatch(r'select\(has\("([A-Za-z_][A-Za-z0-9_-]*)"\)\)', text)
    if has_match:
        return {"op": "filter_has", "path": [has_match.group(1)]}

    eq_match = re.fullmatch(r'select\(\.([A-Za-z_][A-Za-z0-9_.-]*)\s*==\s*"([^"]{0,200})"\)', text)
    if eq_match:
        return {"op": "filter_eq", "path": _json_selector_path(eq_match.group(1)), "value": eq_match.group(2)}

    contains_match = re.fullmatch(
        r'select\(\.([A-Za-z_][A-Za-z0-9_.-]*)\s+contains\s+"([^"]{0,200})"\)',
        text,
    )
    if contains_match:
        return {
            "op": "filter_contains",
            "path": _json_selector_path(contains_match.group(1)),
            "value": contains_match.group(2),
        }

    if text == ".":
        return {"op": "identity"}
    if text == ".[]":
        return {"op": "iterate", "path": []}

    field_match = re.fullmatch(r"\.([A-Za-z_][A-Za-z0-9_.-]*)(\[\])?", text)
    if field_match:
        path = _json_selector_path(field_match.group(1))
        if not path:
            return None
        return {"op": "iterate" if field_match.group(2) else "field", "path": path}

    return None


def _parse_synthetic_jq_stage(stage_tokens: list[str]) -> tuple[dict | None, str | None]:
    stage_tokens = [_unquote_token(token) for token in stage_tokens]
    if stage_tokens[0].lower() != "jq":
        return None, None
    raw = False
    compact = False
    expression = None
    index = 1
    while index < len(stage_tokens):
        token = stage_tokens[index]
        if token in {"-r", "--raw-output"}:
            raw = True
            index += 1
            continue
        if token in {"-c", "--compact-output"}:
            compact = True
            index += 1
            continue
        if expression is not None:
            return None, "Synthetic jq supports a single selector expression."
        expression = token
        index += 1

    selector = _parse_json_selector_expression(expression or "")
    if not selector:
        return None, "Synthetic jq supports only field selectors, array iteration, and simple select filters."
    return {"kind": "jq", "selector": selector, "raw": raw, "compact": compact}, None


def _parse_synthetic_postfilter_stage(stage_tokens: list[str]) -> tuple[dict | None, str | None]:
    for parser in (
        _parse_synthetic_grep_stage,
        _parse_synthetic_head_tail_stage,
        _parse_synthetic_wc_stage,
        _parse_synthetic_sort_stage,
        _parse_synthetic_uniq_stage,
        _parse_synthetic_jq_stage,
    ):
        spec, error = parser(stage_tokens)
        if spec or error:
            return spec, error
    return None, None


def parse_synthetic_postfilter(command: str) -> tuple[dict | None, str | None]:
    """Parse an app-native post-filter pipeline and optional Files sink.

    Returns (spec, error_message). spec is None when the command does not use
    the synthetic post-filter path. error_message is populated only when the
    input is clearly trying to use a supported helper but the stage is invalid.
    """
    stripped = command.strip()
    if '|' not in stripped and '>' not in stripped:
        return None, None
    if '`' in stripped or '$(' in stripped:
        return None, None
    if _FILE_DESCRIPTOR_REDIRECT_RE.search(stripped):
        return None, "Only stdout redirection with `>`, `>>`, or final `| tee` is supported."

    tokens = _split_shell_control_tokens(stripped)
    if not tokens:
        return None, None

    disallowed_control = {'&&', '||', ';', ';;', '<', '&'}
    if any(token in disallowed_control for token in tokens):
        return None, None

    sink = None
    redirect_indexes = [index for index, token in enumerate(tokens) if token in {'>', '>>'}]
    if redirect_indexes:
        if len(redirect_indexes) != 1:
            return None, "Output redirection supports one destination file."
        redirect_index = redirect_indexes[0]
        if redirect_index == 0 or redirect_index != len(tokens) - 2:
            return None, "Output redirection requires `command > file` or `command >> file`."
        destination, destination_error = _output_sink_path(tokens[-1])
        if destination_error:
            return None, destination_error
        assert destination is not None
        sink = {
            "kind": "append" if tokens[redirect_index] == ">>" else "redirect",
            "path": destination,
        }
        tokens = tokens[:redirect_index]

    pipe_indexes = [index for index, token in enumerate(tokens) if token == '|']
    if not pipe_indexes and not sink:
        return None, None

    base_tokens = tokens[:pipe_indexes[0]] if pipe_indexes else tokens
    if not base_tokens:
        return None, "Synthetic post-filters require `command | helper ...`."

    stage_specs: list[dict] = []
    if pipe_indexes:
        stage_start = pipe_indexes[0] + 1
        for stage_number, pipe_index in enumerate(pipe_indexes[1:] + [len(tokens)]):
            stage_tokens = tokens[stage_start:pipe_index]
            if not stage_tokens:
                return None, "Synthetic post-filters require `command | helper ...`."

            helper = _unquote_token(stage_tokens[0]).lower()
            is_final_stage = stage_number == len(pipe_indexes) - 1
            if helper == "tee":
                if sink or not is_final_stage or len(stage_tokens) != 2:
                    return None, "Synthetic tee requires `command | tee file` as the final stage."
                destination, destination_error = _output_sink_path(stage_tokens[1])
                if destination_error:
                    return None, destination_error
                assert destination is not None
                sink = {"kind": "tee", "path": destination}
                stage_start = pipe_index + 1
                continue

            spec, error = _parse_synthetic_postfilter_stage(stage_tokens)
            if error:
                return None, error
            if not spec:
                return None, None

            stage_specs.append(spec)
            stage_start = pipe_index + 1

    return {
        "base_command": shlex.join(_unquote_token(token) for token in base_tokens),
        "stages": stage_specs,
        "kind": stage_specs[0]["kind"] if stage_specs else str((sink or {}).get("kind") or ""),
        "sink": sink,
    }, None
