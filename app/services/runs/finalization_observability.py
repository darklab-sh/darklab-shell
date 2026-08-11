# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Privacy-safe traceback helpers for optional run-finalization stages."""

from __future__ import annotations

import logging
from pathlib import PurePath
from types import TracebackType


def _safe_origin_note(exc: BaseException) -> str:
    frames = []
    traceback = exc.__traceback__
    while traceback is not None:
        code = traceback.tb_frame.f_code
        frames.append(
            f"{PurePath(code.co_filename).name}:{code.co_name}:{traceback.tb_lineno}"
        )
        traceback = traceback.tb_next
    return "Origin frames: " + " > ".join(frames[-12:])[:1000]


def sanitized_finalize_exc_info(
    exc: BaseException,
) -> tuple[type[RuntimeError], RuntimeError, TracebackType | None]:
    """Keep bounded origin frames without copying source or exception text."""
    try:
        raise RuntimeError("Optional run finalization stage failed") from None
    except RuntimeError as safe_error:
        safe_error.add_note(_safe_origin_note(exc))
        return RuntimeError, safe_error, safe_error.__traceback__


def log_finalize_error(
    logger: logging.Logger,
    event: str,
    exc: BaseException,
    finalize_stage: str,
    **fields: object,
) -> None:
    """Emit one bounded finalization failure with a sanitized traceback."""
    logger.error(
        event,
        exc_info=sanitized_finalize_exc_info(exc),
        extra={
            **fields,
            "finalize_stage": finalize_stage,
            "error_class": type(exc).__name__,
        },
    )


__all__ = ["log_finalize_error", "sanitized_finalize_exc_info"]
