# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Line-oriented text comparison and shell-style diff formatting."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal, Sequence, TypeVar


DiffMode = Literal["normal", "brief", "unified", "side_by_side"]
DiffOpcode = tuple[str, int, int, int, int]
SUPPORTED_DIFF_MODES: frozenset[str] = frozenset({"normal", "brief", "unified", "side_by_side"})
SIDE_BY_SIDE_WIDTH = 130

_T = TypeVar("_T")


@dataclass(frozen=True)
class TextDiff:
    different: bool
    lines: tuple[str, ...]


@dataclass(frozen=True)
class _TextLine:
    text: str
    has_newline: bool

    @property
    def match_key(self) -> tuple[str, bool]:
        return self.text, self.has_newline


def sequence_opcodes(left: Sequence[_T], right: Sequence[_T]) -> list[DiffOpcode]:
    """Return deterministic line opcodes shared by comparison surfaces."""

    return list(SequenceMatcher(None, left, right, autojunk=False).get_opcodes())


def grouped_sequence_opcodes(
    left: Sequence[_T],
    right: Sequence[_T],
    *,
    context: int = 3,
) -> list[list[DiffOpcode]]:
    matcher = SequenceMatcher(None, left, right, autojunk=False)
    return [list(group) for group in matcher.get_grouped_opcodes(context)]


def _split_text_lines(text: str) -> list[_TextLine]:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not normalized:
        return []
    values = normalized.split("\n")
    ends_with_newline = values[-1] == ""
    if ends_with_newline:
        values.pop()
    last_index = len(values) - 1
    return [
        _TextLine(value, ends_with_newline or index < last_index)
        for index, value in enumerate(values)
    ]


def _range(start: int, stop: int, *, empty_anchor: bool = False) -> str:
    if start == stop:
        return str(start if empty_anchor else start + 1)
    first = start + 1
    last = stop
    return str(first) if first == last else f"{first},{last}"


def _unified_range(start: int, stop: int) -> str:
    length = stop - start
    first = start + 1
    if length == 0:
        first -= 1
    return str(first) if length == 1 else f"{first},{length}"


def _append_prefixed(lines: list[str], prefix: str, line: _TextLine) -> None:
    lines.append(f"{prefix}{line.text}")
    if not line.has_newline:
        lines.append("\\ No newline at end of file")


def _normal_lines(
    left: list[_TextLine],
    right: list[_TextLine],
    opcodes: Sequence[DiffOpcode],
) -> list[str]:
    output: list[str] = []
    for tag, left_start, left_end, right_start, right_end in opcodes:
        if tag == "equal":
            continue
        if tag == "insert":
            output.append(f"{_range(left_start, left_end, empty_anchor=True)}a{_range(right_start, right_end)}")
            for line in right[right_start:right_end]:
                _append_prefixed(output, "> ", line)
            continue
        if tag == "delete":
            output.append(f"{_range(left_start, left_end)}d{_range(right_start, right_end, empty_anchor=True)}")
            for line in left[left_start:left_end]:
                _append_prefixed(output, "< ", line)
            continue
        output.append(f"{_range(left_start, left_end)}c{_range(right_start, right_end)}")
        for line in left[left_start:left_end]:
            _append_prefixed(output, "< ", line)
        output.append("---")
        for line in right[right_start:right_end]:
            _append_prefixed(output, "> ", line)
    return output


def _unified_lines(
    left: list[_TextLine],
    right: list[_TextLine],
    left_name: str,
    right_name: str,
) -> list[str]:
    left_keys = [line.match_key for line in left]
    right_keys = [line.match_key for line in right]
    groups = grouped_sequence_opcodes(left_keys, right_keys, context=3)
    if not groups:
        return []
    output = [f"--- {left_name}", f"+++ {right_name}"]
    for group in groups:
        first = group[0]
        last = group[-1]
        output.append(
            f"@@ -{_unified_range(first[1], last[2])} "
            f"+{_unified_range(first[3], last[4])} @@"
        )
        for tag, left_start, left_end, right_start, right_end in group:
            if tag == "equal":
                for line in left[left_start:left_end]:
                    _append_prefixed(output, " ", line)
            if tag in {"replace", "delete"}:
                for line in left[left_start:left_end]:
                    _append_prefixed(output, "-", line)
            if tag in {"replace", "insert"}:
                for line in right[right_start:right_end]:
                    _append_prefixed(output, "+", line)
    return output


def _side_fragment(value: str, width: int) -> str:
    return str(value).expandtabs(8)[:width]


def _side_row(left: str, marker: str, right: str, column_width: int) -> str:
    left_text = _side_fragment(left, column_width)
    right_text = _side_fragment(right, column_width)
    return f"{left_text:<{column_width}} {marker} {right_text}".rstrip()


def _side_by_side_lines(
    left: list[_TextLine],
    right: list[_TextLine],
    opcodes: Sequence[DiffOpcode],
    *,
    width: int = SIDE_BY_SIDE_WIDTH,
) -> list[str]:
    column_width = max(1, (max(7, int(width)) - 3) // 2)
    output: list[str] = []
    for tag, left_start, left_end, right_start, right_end in opcodes:
        left_block = left[left_start:left_end]
        right_block = right[right_start:right_end]
        if tag == "equal":
            output.extend(_side_row(item.text, " ", item.text, column_width) for item in left_block)
            continue
        if tag == "delete":
            output.extend(_side_row(item.text, "<", "", column_width) for item in left_block)
            continue
        if tag == "insert":
            output.extend(_side_row("", ">", item.text, column_width) for item in right_block)
            continue
        paired = min(len(left_block), len(right_block))
        output.extend(
            _side_row(left_block[index].text, "|", right_block[index].text, column_width)
            for index in range(paired)
        )
        output.extend(_side_row(item.text, "<", "", column_width) for item in left_block[paired:])
        output.extend(_side_row("", ">", item.text, column_width) for item in right_block[paired:])
    return output


def format_text_diff(
    left_text: str,
    right_text: str,
    *,
    left_name: str,
    right_name: str,
    mode: DiffMode = "normal",
    side_by_side_width: int = SIDE_BY_SIDE_WIDTH,
) -> TextDiff:
    if mode not in SUPPORTED_DIFF_MODES:
        raise ValueError(f"unsupported diff mode: {mode}")
    left = _split_text_lines(left_text)
    right = _split_text_lines(right_text)
    different = left != right
    if not different:
        return TextDiff(different=False, lines=())
    if mode == "brief":
        return TextDiff(different=True, lines=(f"Files {left_name} and {right_name} differ",))

    left_keys = [line.match_key for line in left]
    right_keys = [line.match_key for line in right]
    opcodes = sequence_opcodes(left_keys, right_keys)
    if mode == "unified":
        output = _unified_lines(left, right, left_name, right_name)
    elif mode == "side_by_side":
        output = _side_by_side_lines(left, right, opcodes, width=side_by_side_width)
    else:
        output = _normal_lines(left, right, opcodes)
    return TextDiff(different=True, lines=tuple(output))

