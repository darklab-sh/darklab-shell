# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Safe fields and tracebacks for Project probe observability."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import PurePath
from types import TracebackType
from typing import Any

from services.assessments.probe_contracts import ProbePlanRequest
from services.assessments import probe_log_safety as log_safety
from services.runs.contracts import RunPreparationError, RunStartRejected


def probe_request(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> ProbePlanRequest | None:
    for value in (*args, *kwargs.values()):
        if isinstance(value, ProbePlanRequest):
            return value
    return None


def probe_log_fields(
    phase: str,
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
    *,
    outcome: str,
    error_code: str = "",
    error_class: str = "",
) -> dict[str, Any]:
    request = probe_request(args, kwargs)
    project_id = str(
        request.project_id
        if request
        else kwargs.get("project_id", args[1] if len(args) > 1 else "")
    )
    return {
        "probe_phase": phase,
        "probe_outcome": outcome,
        "project_id": log_safety.safe_probe_id(project_id, "prj"),
        "entity_id": log_safety.safe_probe_id(request.entity_id if request else "", "ent"),
        "action_id": log_safety.safe_probe_action(request.action_id if request else ""),
        "protected": bool(request and request.http_profile_id),
        "error_code": log_safety.safe_probe_code(error_code, "") if error_code else "",
        "error_class": log_safety.safe_probe_error_class(error_class) if error_class else "",
    }


def probe_run_rejection(exc: BaseException) -> tuple[int, str]:
    if isinstance(exc, RunStartRejected):
        return exc.status_code, "run_start_rejected"
    if isinstance(exc, RunPreparationError):
        return exc.status_code, "run_preparation_rejected"
    raise TypeError("Unsupported probe run rejection")


def sanitized_probe_exc_info(
    exc: BaseException,
) -> tuple[type[RuntimeError], RuntimeError, TracebackType | None]:
    frames = []
    traceback = exc.__traceback__
    while traceback is not None:
        code = traceback.tb_frame.f_code
        frames.append(f"{PurePath(code.co_filename).name}:{code.co_name}:{traceback.tb_lineno}")
        traceback = traceback.tb_next
    try:
        raise RuntimeError("Project probe operation failed") from None
    except RuntimeError as safe_error:
        safe_error.add_note("Origin frames: " + " > ".join(frames[-12:])[:1000])
        return RuntimeError, safe_error, safe_error.__traceback__


__all__ = ["probe_log_fields", "probe_request", "probe_run_rejection", "sanitized_probe_exc_info"]
