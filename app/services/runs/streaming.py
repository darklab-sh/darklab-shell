"""Low-level helpers for subprocess stdout streaming."""

from __future__ import annotations

import codecs
import logging
import os
import selectors
from typing import Protocol, TypedDict, cast

log = logging.getLogger("shell")


class _SelectableStream(Protocol):
    def fileno(self) -> int:
        ...


class _ReadableStream(_SelectableStream, Protocol):
    @property
    def encoding(self) -> str | None:
        ...

    @property
    def errors(self) -> str | None:
        ...

    def readline(self) -> str:
        ...


class _ClosableStream(Protocol):
    closed: bool

    def close(self) -> None:
        ...


class _ProcessWithStdout(Protocol):
    stdout: _ClosableStream | None
    returncode: int | None

    def wait(self, timeout: float | None = None) -> int:
        ...


class _StreamReaderState(TypedDict):
    stream: _ReadableStream
    fd: int | None
    decoder: codecs.IncrementalDecoder | None
    pending: str


def timeout_notice(command_timeout: object) -> str:
    return f"[timeout] Command exceeded {command_timeout}s limit and was killed."


def stdout_ready(stream: _SelectableStream | int, timeout: float | None) -> bool:
    sel = selectors.DefaultSelector()
    try:
        sel.register(stream, selectors.EVENT_READ)
        return bool(sel.select(timeout))
    finally:
        sel.close()


def make_nonblocking_stream_reader(stream: _ReadableStream) -> _StreamReaderState:
    fileno = getattr(stream, "fileno", None)
    if not callable(fileno):
        return {"stream": stream, "fd": None, "decoder": None, "pending": ""}
    fd = fileno()
    if not isinstance(fd, int):
        return {"stream": stream, "fd": None, "decoder": None, "pending": ""}
    fd = cast(int, fd)
    try:
        os.set_blocking(fd, False)
    except OSError as exc:
        log.warning("RUN_STREAM_NONBLOCKING_UNAVAILABLE", extra={"fd": fd, "error": str(exc)})
        return {"stream": stream, "fd": None, "decoder": None, "pending": ""}
    encoding = getattr(stream, "encoding", None) or "utf-8"
    errors = getattr(stream, "errors", None) or "replace"
    return {
        "stream": stream,
        "fd": fd,
        "decoder": codecs.getincrementaldecoder(encoding)(errors=errors),
        "pending": "",
    }


def read_available_stream_lines(
    reader_state: _StreamReaderState,
    *,
    finalize: bool = False,
) -> tuple[list[str], bool]:
    if reader_state.get("fd") is None:
        line = reader_state["stream"].readline()
        if line:
            return [line], False
        return [], True

    lines = []
    pending = str(reader_state.get("pending", ""))
    eof = False

    while True:
        try:
            fd = cast(int, reader_state["fd"])
            chunk = os.read(fd, 4096)
        except BlockingIOError:
            break
        if not chunk:
            eof = True
            break
        decoder = reader_state["decoder"]
        if decoder is None:
            return lines, True
        pending += decoder.decode(chunk)
        split = pending.splitlines(keepends=True)
        if split and not split[-1].endswith(("\n", "\r")):
            pending = split.pop()
        else:
            pending = ""
        lines.extend(split)

    if finalize:
        decoder = reader_state["decoder"]
        if decoder is not None:
            pending += decoder.decode(b"", final=True)
        if pending:
            lines.append(pending)
            pending = ""

    reader_state["pending"] = pending
    return lines, eof


def cleanup_proc_stream(proc: _ProcessWithStdout) -> None:
    stdout = getattr(proc, "stdout", None)
    if stdout is not None and not getattr(stdout, "closed", False):
        try:
            stdout.close()
        except Exception:
            pass
    if getattr(proc, "returncode", None) is None:
        wait_for_proc_exit_code(proc)


def wait_for_proc_exit_code(proc: _ProcessWithStdout) -> int | None:
    if getattr(proc, "returncode", None) is not None:
        return proc.returncode
    try:
        return proc.wait(timeout=5)
    except TypeError:
        return proc.wait()
    except Exception:
        return getattr(proc, "returncode", None)
