# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser stream delivery after route authorization."""

from flask import Response

from blueprints import run as run_routes
from services.auth.stream_authorization import authorized_stream


def browser_stream_response(events, *, run_id, team_id, owner_client_id, owner_tab_id, terminate_pty=False):
    stream = authorized_stream(events, run_id=run_id, team_id=team_id, terminate_pty=terminate_pty)

    def generate():
        last_touch_monotonic = None
        try:
            for item in stream:
                if owner_client_id:
                    last_touch_monotonic = run_routes._maybe_touch_active_run_owner(
                        run_id, owner_client_id, owner_tab_id,
                        last_touch_monotonic=last_touch_monotonic,
                    )
                yield item
        finally:
            stream.close()

    return Response(generate(), mimetype="text/event-stream", headers={
        "X-Accel-Buffering": "no", "Cache-Control": "no-cache",
    })
