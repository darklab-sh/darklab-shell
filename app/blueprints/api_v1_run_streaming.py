# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API stream cursor and response construction after scope authorization."""

from flask import Response, request

from blueprints import api_v1 as api_routes
from core.helpers import get_client_ip, get_log_session_id
from services.auth.stream_authorization import authorized_stream


def sse_after_id() -> str:
    explicit = str(request.args.get("after") or "").strip()
    if explicit:
        return explicit
    return str(request.headers.get("Last-Event-ID") or "0-0").strip() or "0-0"


def api_stream_response(run_id, session_id, team_id):
    after_id = api_routes._sse_after_id()
    api_routes.log.debug("API_RUN_STREAM_ATTACHED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "run_id": run_id,
        "team_id": team_id,
        "after_id": after_id,
        "format": str(request.args.get("format") or "sse"),
    })
    stream_log_fields = {
        "ip": get_client_ip(),
        "route": str(request.path or ""),
        "method": str(request.method or ""),
    }
    stream = authorized_stream(
        api_routes.stream_run_events(run_id, after_id=after_id), run_id=run_id, team_id=team_id,
    )
    if str(request.args.get("format") or "").lower() == "ndjson":
        return Response(
            api_routes._ndjson_from_sse_chunks(
                stream,
                run_id=run_id,
                session_id=session_id,
                team_id=team_id,
                **stream_log_fields,
            ),
            mimetype="application/x-ndjson",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
        )
    return Response(
        api_routes._sse_chunks_with_error_logging(
            stream,
            run_id=run_id,
            session_id=session_id,
            team_id=team_id,
            **stream_log_fields,
        ),
        mimetype="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
