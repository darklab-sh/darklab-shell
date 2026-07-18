# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 stream adapter helpers."""

from __future__ import annotations

import json
import logging
from typing import Iterable

from flask import request

from core.helpers import get_log_session_id

log = logging.getLogger("shell")


def sse_after_id() -> str:
    explicit = str(request.args.get("after") or "").strip()
    if explicit:
        return explicit
    return str(request.headers.get("Last-Event-ID") or "0-0").strip() or "0-0"


def log_api_run_stream_error(
    exc: Exception,
    *,
    run_id: str,
    session_id: str,
    team_id: str = "",
    stream_format: str = "sse",
    ip: str = "",
    route: str = "",
    method: str = "",
) -> None:
    log.error(
        "API_RUN_STREAM_ERROR",
        extra={
            "ip": ip,
            "session": get_log_session_id(session_id),
            "run_id": run_id,
            "team_id": team_id,
            "route": route,
            "method": method,
            "format": stream_format,
        },
        exc_info=True,
    )


def ndjson_from_sse_chunks(
    chunks: Iterable[str],
    *,
    run_id: str = "",
    session_id: str = "",
    team_id: str = "",
    ip: str = "",
    route: str = "",
    method: str = "",
):
    try:
        for chunk in chunks:
            if not chunk:
                continue
            for part in chunk.split("\n\n"):
                lines = part.splitlines()
                if lines and all(line.startswith(":") for line in lines if line):
                    yield json.dumps({"type": "heartbeat"}, separators=(",", ":")) + "\n"
                    continue
                data_lines = []
                event_id = ""
                event_type = ""
                for line in lines:
                    if line.startswith("id:"):
                        event_id = line[3:].strip()
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    if line.startswith("data:"):
                        data_lines.append(line[5:].strip())
                if not data_lines:
                    continue
                data = "\n".join(data_lines)
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    log.debug(
                        "API_RUN_STREAM_NDJSON_DECODE_FALLBACK",
                        extra={
                            "run_id": run_id,
                            "session": get_log_session_id(session_id),
                            "team_id": team_id,
                            "event_id": event_id,
                            "event_type": event_type,
                            "payload_bytes": len(data.encode("utf-8")),
                        },
                    )
                    yield data + "\n"
                    continue
                if isinstance(payload, dict):
                    if event_type:
                        payload.setdefault("event", event_type)
                    if event_id:
                        payload.setdefault("event_id", event_id)
                yield json.dumps(payload, separators=(",", ":")) + "\n"
    except Exception as exc:
        if run_id or session_id or team_id:
            log_api_run_stream_error(
                exc,
                run_id=run_id,
                session_id=session_id,
                team_id=team_id,
                stream_format="ndjson",
                ip=ip,
                route=route,
                method=method,
            )
        yield json.dumps({
            "event": "error",
            "code": "stream_error",
            "message": str(exc) or "Run stream interrupted.",
        }) + "\n"


def sse_chunks_with_error_logging(
    chunks: Iterable[str],
    *,
    run_id: str,
    session_id: str,
    team_id: str,
    ip: str,
    route: str,
    method: str,
):
    try:
        yield from chunks
    except Exception as exc:
        log_api_run_stream_error(
            exc,
            run_id=run_id,
            session_id=session_id,
            team_id=team_id,
            stream_format="sse",
            ip=ip,
            route=route,
            method=method,
        )
        payload = json.dumps({
            "event": "error",
            "code": "stream_error",
            "message": str(exc) or "Run stream interrupted.",
        }, separators=(",", ":"))
        yield f"event: error\ndata: {payload}\n\n"
