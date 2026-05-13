"""Terminal capture and ANSI snapshot helpers for interactive PTY runs."""

from __future__ import annotations

import importlib
import logging
import re
import threading
from collections import deque
from collections.abc import Iterable, Sequence
from typing import Any

try:
    # importlib + Any | None lets us treat pyte as optional at runtime without
    # binding a typed module symbol; pyte ships no type stubs.
    pyte: Any | None = importlib.import_module("pyte")
except ImportError:  # pragma: no cover - exercised in deploys after requirements install
    pyte = None

log = logging.getLogger("shell")

_PTY_CAPTURE_MIN_HISTORY_LINES = 2000
_PTY_CAPTURE_MAX_HISTORY_LINES = 10000
_PTY_SNAPSHOT_MAX_BYTES = 128 * 1024
_ANSI_ESCAPE_RE = re.compile(
    r"\x1b(?:"
    r"\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC: ESC ] ... (BEL | ST)
    r"|[PX^_][^\x1b]*\x1b\\"           # DCS / SOS / PM / APC: ESC <intro> ... ST
    r"|\[[0-?]*[ -/]*[@-~]"            # CSI
    r"|[@-Z\\-_]"                      # other 2-char ESC sequences
    r")"
)


def _plain_terminal_text(value: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", value)


def _coerce_non_negative_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        number = value
    elif isinstance(value, float):
        number = int(value)
    elif isinstance(value, (str, bytes, bytearray)):
        try:
            number = int(value)
        except ValueError:
            return default
    else:
        return default
    return number if number >= 0 else default


def _terminal_history_line_limit(value: object) -> int:
    max_output_lines = _coerce_non_negative_int(value, 0)
    if max_output_lines <= 0:
        return _PTY_CAPTURE_MAX_HISTORY_LINES
    return max(
        _PTY_CAPTURE_MIN_HISTORY_LINES,
        min(max_output_lines * 2, _PTY_CAPTURE_MAX_HISTORY_LINES),
    )


def _trim_trailing_blank_lines(lines: list[str]) -> list[str]:
    trimmed = list(lines)
    while trimmed and not trimmed[-1].strip():
        trimmed.pop()
    return trimmed


def _terminal_line_to_text(line: object) -> str:
    if isinstance(line, str):
        return line
    if isinstance(line, dict):
        cells: list[tuple[int, object]] = []
        for key, value in line.items():
            try:
                cells.append((int(key), value))
            except (TypeError, ValueError):
                continue
        return "".join(
            str(getattr(cell, "data", cell) or "")
            for _column, cell in sorted(cells, key=lambda item: item[0])
        )
    values = getattr(line, "values", None)
    if callable(values):
        value_cells = values()
        if isinstance(value_cells, Iterable):
            return "".join(str(getattr(cell, "data", cell) or "") for cell in value_cells)
    return str(line)


_DEFAULT_TERMINAL_ATTRS = ("default", "default", False, False, False, False, False)
_ANSI_COLOR_CODES = {
    "black": 0,
    "red": 1,
    "green": 2,
    "brown": 3,
    "yellow": 3,
    "blue": 4,
    "magenta": 5,
    "cyan": 6,
    "white": 7,
    "brightblack": 8,
    "brightred": 9,
    "brightgreen": 10,
    "brightyellow": 11,
    "brightblue": 12,
    "brightmagenta": 13,
    "brightcyan": 14,
    "brightwhite": 15,
}


def _terminal_line_cells(line: object) -> dict[int, object]:
    if isinstance(line, str):
        return {index: char for index, char in enumerate(line)}
    if isinstance(line, dict):
        cells: dict[int, object] = {}
        for key, value in line.items():
            try:
                cells[int(key)] = value
            except (TypeError, ValueError):
                continue
        return cells
    items = getattr(line, "items", None)
    if callable(items):
        item_pairs = items()
        if not isinstance(item_pairs, Iterable):
            return {}
        cells: dict[int, object] = {}
        for item in item_pairs:
            if not isinstance(item, tuple) or len(item) < 2:
                continue
            key, value = item[0], item[1]
            try:
                cells[int(key)] = value
            except (TypeError, ValueError):
                continue
        return cells
    values = getattr(line, "values", None)
    if callable(values):
        value_cells = values()
        if isinstance(value_cells, Iterable):
            return {index: cell for index, cell in enumerate(value_cells)}
    text = str(line)
    return {index: char for index, char in enumerate(text)}


def _terminal_cell_data(cell: object) -> str:
    return str(getattr(cell, "data", cell) or "")


def _terminal_cell_attrs(cell: object) -> tuple[object, object, bool, bool, bool, bool, bool]:
    return (
        getattr(cell, "fg", "default") or "default",
        getattr(cell, "bg", "default") or "default",
        bool(getattr(cell, "bold", False)),
        bool(getattr(cell, "italics", False) or getattr(cell, "italic", False)),
        bool(getattr(cell, "underscore", False) or getattr(cell, "underline", False)),
        bool(getattr(cell, "strikethrough", False)),
        bool(getattr(cell, "reverse", False)),
    )


def _terminal_color_code(value: object, base: int) -> list[int]:
    if value in (None, "", "default"):
        return []
    if isinstance(value, int):
        return [base + 8, 5, max(0, min(value, 255))]
    if isinstance(value, (tuple, list)) and len(value) >= 3:
        try:
            red, green, blue = [max(0, min(int(part), 255)) for part in value[:3]]
        except (TypeError, ValueError):
            return []
        return [base + 8, 2, red, green, blue]
    key = str(value).lower().replace("_", "").replace("-", "")
    if key not in _ANSI_COLOR_CODES:
        return []
    code = _ANSI_COLOR_CODES[key]
    return [base + code] if code < 8 else [base + 60 + (code - 8)]


def _terminal_attrs_to_sgr(attrs: tuple[object, object, bool, bool, bool, bool, bool]) -> str:
    if attrs == _DEFAULT_TERMINAL_ATTRS:
        return "\x1b[0m"
    fg, bg, bold, italics, underscore, strikethrough, reverse = attrs
    codes: list[int] = []
    if bold:
        codes.append(1)
    if italics:
        codes.append(3)
    if underscore:
        codes.append(4)
    if reverse:
        codes.append(7)
    if strikethrough:
        codes.append(9)
    codes.extend(_terminal_color_code(fg, 30))
    codes.extend(_terminal_color_code(bg, 40))
    return f"\x1b[{';'.join(str(code) for code in codes) or '0'}m"


def _terminal_row_to_ansi(line: object, cols: int) -> str:
    cells = _terminal_line_cells(line)
    if not cells:
        return ""
    last_col = -1
    for column, cell in cells.items():
        if column < 0 or column >= cols:
            continue
        data = _terminal_cell_data(cell)
        attrs = _terminal_cell_attrs(cell)
        if data.strip() or attrs != _DEFAULT_TERMINAL_ATTRS:
            last_col = max(last_col, column)
    if last_col < 0:
        return ""

    current_attrs = _DEFAULT_TERMINAL_ATTRS
    chunks: list[str] = []
    for column in range(last_col + 1):
        cell = cells.get(column, " ")
        data = _terminal_cell_data(cell)[:1] or " "
        attrs = _terminal_cell_attrs(cell)
        if attrs != current_attrs:
            chunks.append(_terminal_attrs_to_sgr(attrs))
            current_attrs = attrs
        chunks.append(data)
    if current_attrs != _DEFAULT_TERMINAL_ATTRS:
        chunks.append("\x1b[0m")
    return "".join(chunks)


def _bounded_ansi_snapshot(
    scrollback_rows: Sequence[object],
    screen_rows: Sequence[object],
    rows: int,
    cols: int,
    cursor_y: int,
    cursor_x: int,
    max_bytes: int = _PTY_SNAPSHOT_MAX_BYTES,
) -> tuple[str, bool]:
    screen_lines = [_terminal_row_to_ansi(line, cols) for line in screen_rows]
    cursor_y = max(0, min(cursor_y, max(0, rows - 1)))
    cursor_x = max(0, min(cursor_x, max(0, cols - 1)))
    suffix = f"\x1b[0m\x1b[{cursor_y + 1};{cursor_x + 1}H"

    used = len("\x1b[0m\x1b[2J\x1b[H".encode("utf-8")) + len(suffix.encode("utf-8"))
    screen_bytes = sum(len(line.encode("utf-8")) + len("\r\n".encode("utf-8")) for line in screen_lines)
    budget = max(0, max_bytes - used - screen_bytes)
    scrollback_tail: list[str] = []
    truncated = False
    for line in reversed(scrollback_rows):
        ansi_line = _terminal_row_to_ansi(line, cols)
        line_bytes = len(ansi_line.encode("utf-8")) + len("\r\n".encode("utf-8"))
        if line_bytes > budget:
            truncated = True
            break
        scrollback_tail.append(ansi_line)
        budget -= line_bytes
    if len(scrollback_tail) < len(scrollback_rows):
        truncated = True

    lines = list(reversed(scrollback_tail)) + screen_lines
    snapshot = "\x1b[0m\x1b[2J\x1b[H" + "\r\n".join(lines) + suffix
    return snapshot, truncated


class PtyTerminalCapture:
    """Server-side terminal view used only for saved PTY history."""

    def __init__(self, rows: int, cols: int, history_lines: int):
        self.rows = rows
        self.cols = cols
        self.history_lines = max(0, int(history_lines or 0))
        self._lock = threading.Lock()
        self._screen = None
        self._stream = None
        self._stream_failed = False
        self._fallback_pending = ""
        self._fallback_cursor_col = 0
        self._fallback_lines: deque[str] = deque(maxlen=max(1, self.history_lines + rows))
        pyte_module = pyte
        if pyte_module is None:
            return
        try:
            self._screen = pyte_module.HistoryScreen(cols, rows, history=self.history_lines)
            self._stream = pyte_module.Stream(self._screen)
        except Exception:
            log.warning("PTY_CAPTURE_INIT_FAILED", exc_info=True)
            self._screen = None
            self._stream = None

    def feed(self, text: str) -> None:
        if not text:
            return
        with self._lock:
            if self._stream is not None and not self._stream_failed:
                try:
                    self._stream.feed(text)
                    return
                except Exception:
                    self._stream_failed = True
                    self._screen = None
                    self._stream = None
                    log.warning("PTY_CAPTURE_FEED_FAILED", exc_info=True)
            self._feed_fallback(text)

    def resize(self, rows: int, cols: int) -> None:
        with self._lock:
            self.rows = rows
            self.cols = cols
            if self._screen is None:
                return
            resize = getattr(self._screen, "resize", None)
            if not callable(resize):
                return
            try:
                resize(lines=rows, columns=cols)
            except TypeError:
                resize(rows, cols)
            except Exception:
                log.warning("PTY_CAPTURE_RESIZE_FAILED", exc_info=True)

    def synthesize_entries(self) -> list[dict[str, str]]:
        with self._lock:
            scrollback = self._scrollback_lines()
            final_frame = self._final_frame_lines()
        entries = [{"text": line, "cls": ""} for line in scrollback]
        if scrollback and final_frame:
            entries.append({"text": "", "cls": "pty-marker"})
        entries.extend({"text": line, "cls": ""} for line in final_frame)
        if entries:
            return entries
        return [{"text": "[interactive PTY exited with no output]", "cls": "notice"}]

    def ansi_snapshot(self) -> tuple[str, bool]:
        with self._lock:
            if self._screen is None:
                return "", False
            history = getattr(self._screen, "history", None)
            scrollback_rows = list(getattr(history, "top", []) if history is not None else [])
            buffer = getattr(self._screen, "buffer", None)
            if isinstance(buffer, dict):
                screen_rows = [buffer.get(row, "") for row in range(self.rows)]
            else:
                display = list(getattr(self._screen, "display", []))
                screen_rows = display[:self.rows]
            cursor = getattr(self._screen, "cursor", None)
            cursor_y = _coerce_non_negative_int(getattr(cursor, "y", 0), 0)
            cursor_x = _coerce_non_negative_int(getattr(cursor, "x", 0), 0)
        return _bounded_ansi_snapshot(
            scrollback_rows,
            screen_rows,
            self.rows,
            self.cols,
            cursor_y,
            cursor_x,
        )

    def _feed_fallback(self, text: str) -> None:
        plain = _plain_terminal_text(text)
        if not plain:
            return
        i = 0
        while i < len(plain):
            char = plain[i]
            if char == "\r":
                if i + 1 < len(plain) and plain[i + 1] == "\n":
                    self._fallback_commit_line()
                    i += 2
                    continue
                self._fallback_cursor_col = 0
            elif char == "\n":
                self._fallback_commit_line()
            elif char == "\b":
                self._fallback_cursor_col = max(0, self._fallback_cursor_col - 1)
            else:
                self._fallback_write_char(char)
            i += 1

    def _fallback_commit_line(self) -> None:
        self._fallback_lines.append(self._fallback_pending.rstrip())
        self._fallback_pending = ""
        self._fallback_cursor_col = 0

    def _fallback_write_char(self, char: str) -> None:
        cursor = self._fallback_cursor_col
        pending = self._fallback_pending
        if cursor < len(pending):
            self._fallback_pending = f"{pending[:cursor]}{char}{pending[cursor + 1:]}"
        else:
            if cursor > len(pending):
                self._fallback_pending += " " * (cursor - len(pending))
            self._fallback_pending += char
        self._fallback_cursor_col = cursor + 1

    def _scrollback_lines(self) -> list[str]:
        if self._screen is not None:
            history = getattr(self._screen, "history", None)
            top = getattr(history, "top", []) if history is not None else []
            # pyte history rows are cell mappings; display rows below are already strings.
            return [_terminal_line_to_text(line).rstrip() for line in list(top)]
        lines = list(self._fallback_lines)
        if self._fallback_pending:
            lines.append(self._fallback_pending.rstrip())
        return _trim_trailing_blank_lines(lines)

    def _final_frame_lines(self) -> list[str]:
        if self._screen is None:
            return []
        display = getattr(self._screen, "display", [])
        return _trim_trailing_blank_lines([str(line).rstrip() for line in list(display)])
