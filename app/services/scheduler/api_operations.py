# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Schedule operations shared by API routes."""

from __future__ import annotations

from typing import Any

from services.audit.automation import record_schedule_event, run_now_details
from services.audit.models import AuditEventType
from services.scheduler.route_helpers import fire_schedule_now
from services.scheduler.service import create_schedule, delete_schedule, update_schedule
from services.storage.transactions import run_transaction
from core import database


def _run_schedule_api_transaction(callback):
    return run_transaction(callback, connect=database.db_connect)


def create_schedule_for_api(session_id: str, *, team_id: str, payload: dict[str, Any], audit_fields: dict[str, Any]):
    def _create(conn):
        schedule = create_schedule(session_id, team_id=team_id, **payload, conn=conn)
        record_schedule_event(
            AuditEventType.SCHEDULE_CREATE,
            schedule,
            audit_fields=audit_fields,
            source="api_v1",
            conn=conn,
        )
        return schedule

    return _run_schedule_api_transaction(_create)


def update_schedule_for_api(schedule_id: str, updates: dict[str, Any], *, audit_fields: dict[str, Any]):
    def _update(conn):
        updated = update_schedule(schedule_id, updates, conn=conn)
        if updated is not None:
            record_schedule_event(
                AuditEventType.SCHEDULE_UPDATE,
                updated,
                audit_fields=audit_fields,
                source="api_v1",
                details={"changed_fields": sorted(key for key in updates if key != "workspace_cwd")},
                conn=conn,
            )
        return updated

    return _run_schedule_api_transaction(_update)


def delete_schedule_for_api(schedule, *, audit_fields: dict[str, Any]) -> bool:
    def _delete(conn):
        removed = delete_schedule(schedule.id, conn=conn)
        record_schedule_event(
            AuditEventType.SCHEDULE_DELETE,
            schedule,
            audit_fields=audit_fields,
            source="api_v1",
            details={"deleted_count": 1 if removed else 0},
            conn=conn,
        )
        return removed

    return _run_schedule_api_transaction(_delete)


def fire_schedule_now_for_api(schedule, *, audit_fields: dict[str, Any]):
    def _fire(conn):
        status, refreshed, fired_at = fire_schedule_now(conn, schedule)
        record_schedule_event(
            AuditEventType.SCHEDULE_RUN_NOW,
            refreshed or schedule,
            audit_fields=audit_fields,
            source="api_v1",
            details=run_now_details(
                status,
                fired_at=fired_at,
                run_id=(refreshed or schedule).last_run_id,
                last_error=(refreshed or schedule).last_error,
            ),
            conn=conn,
        )
        return status, refreshed, fired_at

    return _run_schedule_api_transaction(_fire)

