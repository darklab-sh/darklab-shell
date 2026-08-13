# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Caller-neutral correlation fields for Project probe records."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from core.helpers import get_log_session_id
from services.assessments.probe_contracts import PROBE_POLICY_LEVELS
from services.assessments.probe_log_safety import safe_probe_id


_SOURCES = frozenset({"api_v1", "browser_terminal"})
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


def _token(value: object) -> str:
    candidate = str(value or "").strip()
    return candidate if _TOKEN_RE.fullmatch(candidate) else ""


@dataclass(frozen=True)
class ProbeLogContext:
    """Safe request correlation supplied by a browser or API adapter."""

    source: str
    request_id: str
    session_id: str
    team_id: str = ""


def probe_context_fields(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> dict[str, str]:
    context = next(
        (value for value in (*args, *kwargs.values()) if isinstance(value, ProbeLogContext)),
        None,
    )
    if context is None:
        return {"source": "", "request_id": "", "session": "", "team_id": ""}
    session_id = _token(context.session_id)
    return {
        "source": context.source if context.source in _SOURCES else "unknown",
        "request_id": _token(context.request_id),
        "session": get_log_session_id(session_id) if session_id else "",
        "team_id": safe_probe_id(context.team_id, "team") if context.team_id else "",
    }


def probe_result_fields(result: Any) -> dict[str, str]:
    plan = getattr(result, "plan", result if isinstance(result, Mapping) else {})
    started = getattr(result, "started", None)
    policy = str(plan.get("policy_level") or "") if isinstance(plan, Mapping) else ""
    return {
        "policy_level": policy if policy in PROBE_POLICY_LEVELS else "",
        "run_id": _token(getattr(started, "run_id", "")),
    }


__all__ = ["ProbeLogContext", "probe_context_fields", "probe_result_fields"]
