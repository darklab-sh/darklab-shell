"""Watcher operations shared by API routes."""

from __future__ import annotations

from typing import Any

from services.api_v1.auth import ApiAuthError
from services.audit.automation import record_watcher_event, run_now_details
from services.audit.models import AuditEventType
from services.scheduler.route_helpers import fire_watcher_now, normalize_watcher_create_payload
from services.scheduler.service import get_schedule
from services.storage.transactions import run_read, run_transaction
from services.watchers.service import (
    accept_baseline,
    create_watcher,
    delete_watcher,
    get_watcher,
    list_for_owner,
    list_watcher_fires,
    pause_watcher,
    resume_watcher,
    update_watcher,
)
from core import database


def _run_watcher_api_read(callback):
    return run_read(callback, connect=database.db_connect)


def _run_watcher_api_transaction(callback):
    return run_transaction(callback, connect=database.db_connect)


def watcher_for_api_session(watcher_id: str, session_id: str, *, team_id: str = "", conn=None):
    watcher = get_watcher(watcher_id, conn=conn)
    if watcher is None:
        raise ApiAuthError("not_found", "Watcher not found.", status_code=404)
    if team_id:
        if watcher.team_id != team_id:
            raise ApiAuthError("not_found", "Watcher not found.", status_code=404)
        return watcher
    if watcher.team_id or watcher.session_token != session_id:
        raise ApiAuthError("not_found", "Watcher not found.", status_code=404)
    return watcher


def list_watchers_for_api(session_id: str, *, team_id: str):
    def _list(conn):
        watchers = list_for_owner(session_id, team_id=team_id, conn=conn)
        schedules = {watcher.schedule_id: get_schedule(watcher.schedule_id, conn=conn) for watcher in watchers}
        return watchers, schedules

    return _run_watcher_api_read(_list)


def watcher_detail_for_api(watcher_id: str, session_id: str, *, team_id: str):
    def _detail(conn):
        watcher = watcher_for_api_session(watcher_id, session_id, team_id=team_id, conn=conn)
        schedule = get_schedule(watcher.schedule_id, conn=conn)
        return watcher, schedule

    return _run_watcher_api_read(_detail)


def create_watcher_from_body_for_api(
    session_id: str,
    *,
    team_id: str,
    data: dict[str, Any],
    command_validator,
    audit_fields: dict[str, Any],
):
    def _create(conn):
        payload = normalize_watcher_create_payload(
            data,
            session_id,
            team_id=team_id,
            conn=conn,
            command_validator=command_validator,
        )
        watcher = create_watcher(session_id, team_id=team_id, **payload, conn=conn)
        schedule = get_schedule(watcher.schedule_id, conn=conn)
        record_watcher_event(
            AuditEventType.WATCHER_CREATE,
            watcher,
            audit_fields=audit_fields,
            source="api_v1",
            conn=conn,
        )
        return watcher, schedule

    return _run_watcher_api_transaction(_create)


def update_watcher_for_api(
    watcher_id: str,
    session_id: str,
    *,
    team_id: str,
    route_update,
    audit_fields: dict[str, Any],
):
    def _update(conn):
        watcher = watcher_for_api_session(watcher_id, session_id, team_id=team_id, conn=conn)
        updated = update_watcher(watcher.id, route_update.updates, conn=conn) if route_update.updates else watcher
        if updated is None:
            raise ApiAuthError("not_found", "Watcher not found.", status_code=404)
        event_type = AuditEventType.WATCHER_UPDATE
        if route_update.pause_requested:
            updated = pause_watcher(updated.id, route_update.reason, conn=conn)
            event_type = AuditEventType.WATCHER_PAUSE
        elif route_update.resume_requested:
            updated = resume_watcher(updated.id, conn=conn)
            event_type = AuditEventType.WATCHER_RESUME
        if updated is None:
            raise ApiAuthError("not_found", "Watcher not found.", status_code=404)
        schedule = get_schedule(updated.schedule_id, conn=conn)
        record_watcher_event(
            event_type,
            updated,
            audit_fields=audit_fields,
            source="api_v1",
            details={
                "changed_fields": sorted(key for key in route_update.updates if key != "workspace_cwd"),
                "reason": route_update.reason if route_update.pause_requested else "",
            },
            conn=conn,
        )
        return updated, schedule

    return _run_watcher_api_transaction(_update)


def delete_watcher_for_api(watcher_id: str, session_id: str, *, team_id: str, audit_fields: dict[str, Any]):
    def _delete(conn):
        watcher = watcher_for_api_session(watcher_id, session_id, team_id=team_id, conn=conn)
        removed = delete_watcher(watcher.id, conn=conn)
        record_watcher_event(
            AuditEventType.WATCHER_DELETE,
            watcher,
            audit_fields=audit_fields,
            source="api_v1",
            details={"deleted_count": 1 if removed else 0},
            conn=conn,
        )
        return watcher, removed

    return _run_watcher_api_transaction(_delete)


def fire_watcher_now_for_api(watcher_id: str, session_id: str, *, team_id: str, audit_fields: dict[str, Any]):
    def _fire(conn):
        watcher = watcher_for_api_session(watcher_id, session_id, team_id=team_id, conn=conn)
        status, refreshed, refreshed_schedule, fired_at = fire_watcher_now(conn, watcher)
        record_watcher_event(
            AuditEventType.WATCHER_RUN_NOW,
            refreshed,
            audit_fields=audit_fields,
            source="api_v1",
            details=run_now_details(
                status,
                fired_at=fired_at,
                run_id=refreshed.last_run_id,
                last_error=refreshed.last_error,
            ),
            conn=conn,
        )
        return status, refreshed, refreshed_schedule, fired_at

    return _run_watcher_api_transaction(_fire)


def watcher_fires_for_api(watcher_id: str, session_id: str, *, team_id: str, limit: int, offset: int):
    def _fires(conn):
        watcher = watcher_for_api_session(watcher_id, session_id, team_id=team_id, conn=conn)
        fires, total = list_watcher_fires(watcher.id, limit=limit, offset=offset, conn=conn)
        return watcher, fires, total

    return _run_watcher_api_read(_fires)


def accept_watcher_baseline_for_api(
    watcher_id: str,
    session_id: str,
    *,
    team_id: str,
    run_id: str | None,
    audit_fields: dict[str, Any],
):
    def _accept(conn):
        watcher = watcher_for_api_session(watcher_id, session_id, team_id=team_id, conn=conn)
        accepted = accept_baseline(watcher.id, run_id=run_id, conn=conn)
        if accepted is None:
            raise ApiAuthError("not_found", "Watcher not found.", status_code=404)
        schedule = get_schedule(accepted.schedule_id, conn=conn)
        record_watcher_event(
            AuditEventType.WATCHER_ACCEPT_BASELINE,
            accepted,
            audit_fields=audit_fields,
            source="api_v1",
            details={"baseline_run_id": accepted.baseline_run_id},
            conn=conn,
        )
        return accepted, schedule

    return _run_watcher_api_transaction(_accept)
