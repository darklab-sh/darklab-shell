"""Redis-backed PTY state helpers."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from config import resolve_effective_cfg
import core.process as process_state
from core.process import RedisClientProxy as RedisClientProxy
from services.pty.snapshots import pty_snapshot_wire_entries
from services.pty.wire import control_key as _control_key
from services.pty.wire import meta_key as _meta_key
from services.pty.wire import snapshot_key as _snapshot_key
from services.pty.wire import stream_key as _stream_key

log = logging.getLogger("shell")


def _redis_client(redis_client: Any | None = None) -> Any | None:
    return redis_client if redis_client is not None else process_state.redis_client


def active_ttl() -> int:
    return max(1, int(resolve_effective_cfg().get("run_broker_active_stream_ttl_seconds", 14400) or 14400))


def completed_ttl() -> int:
    return max(1, int(resolve_effective_cfg().get("run_broker_completed_stream_ttl_seconds", 3600) or 3600))


def store_pty_meta(run: Any, *, redis_client: Any | None = None, closed: bool = False) -> None:
    redis_client = _redis_client(redis_client)
    if not redis_client:
        return
    payload = {
        "run_id": run.run_id,
        "session_id": run.session_id,
        "team_id": run.team_id,
        "command": run.command,
        "started": run.started,
        "rows": run.rows,
        "cols": run.cols,
        "closed": bool(closed),
    }
    redis_client.set(
        _meta_key(run.run_id),
        json.dumps(payload, separators=(",", ":")),
        ex=completed_ttl() if closed else active_ttl(),
    )
    if closed:
        redis_client.delete(_control_key(run.run_id), _snapshot_key(run.run_id))


def safe_store_pty_meta(run: Any, *, redis_client: Any | None = None, closed: bool = False) -> bool:
    try:
        store_pty_meta(run, redis_client=redis_client, closed=closed)
        return True
    except Exception as exc:
        log.error("PTY_META_SAVE_FAILED", exc_info=True, extra={
            "run_id": run.run_id,
            "session": run.session_id,
            "team_id": run.team_id,
            "cmd": run.command,
            "closed": bool(closed),
            "error": str(exc),
        })
        return False


def delete_pty_meta(run_id: str, *, redis_client: Any | None = None) -> None:
    redis_client = _redis_client(redis_client)
    if not redis_client:
        return
    redis_client.delete(_meta_key(run_id))
    redis_client.delete(_control_key(run_id))
    redis_client.delete(_snapshot_key(run_id))


def delete_pty_runtime_state(
    run_id: str,
    *,
    redis_client: Any | None = None,
    include_stream: bool = False,
) -> None:
    redis_client = _redis_client(redis_client)
    if not redis_client:
        return
    keys = [_meta_key(run_id), _control_key(run_id), _snapshot_key(run_id)]
    if include_stream:
        keys.append(_stream_key(run_id))
    redis_client.delete(*keys)


def meta_matches_scope(meta: dict[str, Any], session_id: str, team_id: str = "") -> bool:
    if team_id:
        return str(meta.get("team_id", "") or "") == str(team_id)
    return (
        str(meta.get("session_id", "")) == session_id
        and str(meta.get("team_id", "") or "") == ""
    )


def load_pty_snapshot(
    run_id: str,
    session_id: str,
    team_id: str = "",
    *,
    redis_client: Any | None = None,
) -> dict[str, Any] | None:
    redis_client = _redis_client(redis_client)
    if not redis_client:
        return None
    raw = redis_client.get(_snapshot_key(run_id))
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if not isinstance(raw, str):
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not meta_matches_scope(payload, session_id, team_id):
        return None
    response = dict(payload)
    response["entries"] = pty_snapshot_wire_entries(response.get("entries") or [])
    try:
        created_at = float(response.get("created_at", 0) or 0)
    except (TypeError, ValueError):
        created_at = 0
    if created_at:
        response["snapshot_age_seconds"] = round(max(0.0, time.time() - created_at), 3)
    else:
        response["snapshot_age_seconds"] = None
    response.pop("session_id", None)
    response.pop("team_id", None)
    response.pop("created_at", None)
    return response
