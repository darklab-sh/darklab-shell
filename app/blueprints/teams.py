# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser routes for team-mode management."""

from __future__ import annotations

import logging
from typing import Any

from flask import Blueprint, jsonify, request

from config import CFG
from core.helpers import get_client_ip, get_log_session_id, get_session_id
from extensions import limiter
from services.audit.context import request_audit_fields
from services.audit.models import AuditEventType
from services.audit.queries import AuditEventFilters, AuditScopeError, list_scoped_events
from services.audit.recorder import record_event
from services.audit.retention import audit_retention_days
from services.teams import storage
from services.teams.capabilities import Capability, require_capability
from services.teams.contracts import (
    TeamError,
    TeamArchived,
    TeamNotFound,
    TeamOwnerRequired,
    TeamPermissionDenied,
    TeamSlugUnavailable,
)
from services.teams.request_scope import RequestScope
from services.teams.scope import team_owner_context
from services.watchers.service import pause_team_watchers_and_schedules

teams_bp = Blueprint("teams", __name__)
log = logging.getLogger("shell")


def _team_read_route_limit():
    minute_limit = int(CFG.get("team_read_rate_limit_per_minute") or 180)
    second_limit = int(CFG.get("team_read_rate_limit_per_second") or 20)
    return f"{minute_limit} per minute; {second_limit} per second"


def _team_write_route_limit():
    limit = int(CFG.get("team_write_rate_limit_per_minute") or 30)
    return f"{limit} per minute"


def _parse_int(value, default, *, minimum=0, maximum=100):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _required_token_session():
    session_id = get_session_id()
    if not session_id:
        return "", (jsonify({"error": "session_required"}), 401)
    if not str(session_id).startswith("tok_"):
        return "", (jsonify({"error": "session_token_required"}), 401)
    return session_id, None


def _json_body() -> tuple[dict[str, Any], Any]:
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return {}, (jsonify({"error": "Request body must be a JSON object"}), 400)
    return data, None


def _team_error_code_and_status(exc: Exception) -> tuple[str, int]:
    if isinstance(exc, TeamPermissionDenied):
        return "team_forbidden", 403
    if isinstance(exc, TeamOwnerRequired):
        return "team_owner_required", 409
    if isinstance(exc, TeamSlugUnavailable):
        return "team_slug_unavailable", 409
    if isinstance(exc, TeamArchived):
        return "team_archived", 409
    if isinstance(exc, TeamNotFound):
        return "team_not_found", 404
    if isinstance(exc, (TeamError, ValueError)):
        return "invalid_team_request", 400
    return "team_route_failed", 500


def _team_error(exc: Exception):
    code, status = _team_error_code_and_status(exc)
    payload = {"error": code}
    if status < 500:
        payload["message"] = str(exc)
    return jsonify(payload), status


def _actor_membership(conn, team_id: str, session_token: str) -> dict[str, Any]:
    membership = storage.get_team_membership(conn, team_id, session_token)
    if not membership:
        raise TeamNotFound("Team not found")
    return membership


def _actor_log_fields(actor: dict[str, Any] | None) -> dict[str, Any]:
    if not actor:
        return {}
    return {
        "actor_member_id": str(actor.get("id") or ""),
        "actor_role": str(actor.get("role") or ""),
    }


def _actor_audit_fields(
    session_token: str,
    *,
    team_id: str = "",
    actor: dict[str, Any] | None = None,
    actor_member_id: str = "",
    actor_role: str = "",
    actor_display_name: str = "",
) -> dict[str, Any]:
    actor_member_id = actor_member_id or str((actor or {}).get("id") or "")
    actor_role = actor_role or str((actor or {}).get("role") or "")
    actor_display_name = actor_display_name or str(
        (actor or {}).get("display_name") or (actor or {}).get("name") or ""
    )
    return {
        "session_id": session_token,
        "actor_session_id": session_token,
        "team_id": team_id,
        "actor_member_id": actor_member_id,
        "actor_role": actor_role,
        "actor_display_name": actor_display_name,
        **request_audit_fields(request),
    }


def _record_team_audit(
    event_type: AuditEventType,
    *,
    session_token: str,
    team_id: str,
    actor: dict[str, Any] | None = None,
    actor_member_id: str = "",
    actor_role: str = "",
    actor_display_name: str = "",
    details: dict[str, Any] | None = None,
    conn=None,
) -> None:
    record_event(
        event_type,
        target_id=team_id,
        details={"source": "browser", **(details or {})},
        conn=conn,
        **_actor_audit_fields(
            session_token,
            team_id=team_id,
            actor=actor,
            actor_member_id=actor_member_id,
            actor_role=actor_role,
            actor_display_name=actor_display_name,
        ),
    )


def _team_log_fields(
    action: str,
    *,
    session_token: str,
    team_id: str = "",
    result: str = "ok",
    actor: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "action": action,
        "team_id": team_id,
        "session": get_log_session_id(session_token),
        "ip": get_client_ip(),
        "result": result,
        "source": "browser",
        "route": str(request.path or ""),
        "method": str(request.method or ""),
        **_actor_log_fields(actor),
        **extra,
    }


def _log_team_event(
    action: str,
    *,
    session_token: str,
    team_id: str = "",
    result: str = "ok",
    actor: dict[str, Any] | None = None,
    **extra: Any,
) -> None:
    fields = _team_log_fields(action, session_token=session_token, team_id=team_id, result=result, actor=actor, **extra)
    if result == "ok":
        log.info("TEAM_ACTION", extra=fields)
    else:
        log.warning("TEAM_ACTION_REJECTED", extra=fields)


def _log_team_exception(
    action: str,
    exc: Exception,
    *,
    session_token: str,
    team_id: str = "",
    actor: dict[str, Any] | None = None,
    **extra: Any,
):
    code, status = _team_error_code_and_status(exc)
    fields = _team_log_fields(
        action,
        session_token=session_token,
        team_id=team_id,
        result="error",
        actor=actor,
        reason=code,
        error_code=code,
        http_status=status,
        **extra,
    )
    if status >= 500:
        log.error("TEAM_ROUTE_FAILED", extra=fields, exc_info=True)
    else:
        log.warning("TEAM_ACTION_REJECTED", extra=fields)
    return _team_error(exc)


@teams_bp.route("/session/teams", methods=["GET"])
@limiter.limit(_team_read_route_limit, key_func=get_session_id)
def session_teams_list():
    session_token, error_response = _required_token_session()
    if error_response:
        return error_response
    teams = storage.run_team_read(lambda conn: storage.list_teams_for_token(conn, session_token))
    return jsonify({"teams": teams})


@teams_bp.route("/session/teams", methods=["POST"])
@limiter.limit(_team_write_route_limit, key_func=get_session_id)
def session_teams_create():
    session_token, error_response = _required_token_session()
    if error_response:
        return error_response
    data, body_error = _json_body()
    if body_error:
        return body_error
    try:
        def _create(conn):
            team, recovery = storage.create_team_with_recovery_code(
                conn,
                name=str(data.get("name") or ""),
                slug=str(data.get("slug") or ""),
                creator_session_token=session_token,
                display_name=str(data.get("display_name") or ""),
            )
            detail = storage.team_detail(conn, team["id"], current_session_token=session_token)
            _record_team_audit(
                AuditEventType.TEAM_CREATE,
                session_token=session_token,
                team_id=team["id"],
                actor_member_id=team.get("creator_member_id", ""),
                actor_role="owner",
                details={"role": "owner"},
                conn=conn,
            )
            return team, recovery, detail

        team, recovery, detail = storage.run_team_transaction(_create)
        _log_team_event(
            "create",
            session_token=session_token,
            team_id=team["id"],
            actor_member_id=team.get("creator_member_id", ""),
            actor_role="owner",
        )
        return jsonify({"team": (detail or {}).get("team", {}), "recovery_code": recovery["code"]}), 201
    except Exception as exc:
        return _log_team_exception("create", exc, session_token=session_token)


@teams_bp.route("/session/teams/<team_id>", methods=["GET"])
@limiter.limit(_team_read_route_limit, key_func=get_session_id)
def session_teams_detail(team_id):
    session_token, error_response = _required_token_session()
    if error_response:
        return error_response
    actor = None
    try:
        def _detail(conn):
            nonlocal actor
            actor = _actor_membership(conn, team_id, session_token)
            return storage.team_detail(conn, team_id, current_session_token=session_token)

        detail = storage.run_team_read(_detail)
        if not detail:
            raise TeamNotFound("Team not found")
        return jsonify(detail)
    except Exception as exc:
        return _log_team_exception("detail", exc, session_token=session_token, team_id=team_id, actor=actor)


@teams_bp.route("/session/teams/<team_id>/activity", methods=["GET"])
@limiter.limit(_team_read_route_limit, key_func=get_session_id)
def session_teams_activity(team_id):
    session_token, error_response = _required_token_session()
    if error_response:
        return error_response
    actor = None
    try:
        def _membership(conn):
            actor = _actor_membership(conn, team_id, session_token)
            return actor

        actor = storage.run_team_read(_membership)
        scope = RequestScope(
            team_owner_context(
                team_id,
                actor_member_id=str(actor.get("id") or ""),
                actor_session_id=session_token,
            ),
            team_id=team_id,
            member=actor,
            team_status=str(actor.get("team_status") or ""),
            read_only=str(actor.get("team_status") or "") == "archived",
        )
        payload = list_scoped_events(
            session_token,
            scope,
            AuditEventFilters(
                event_type=str(request.args.get("event_type") or "").strip(),
                actor=str(request.args.get("actor") or "").strip(),
                target_type=str(request.args.get("target_type") or "").strip(),
                target_id=str(request.args.get("target_id") or "").strip(),
                date_from=str(request.args.get("date_from") or "").strip(),
                date_to=str(request.args.get("date_to") or "").strip(),
            ),
            include_team_activity=True,
            limit=_parse_int(request.args.get("limit"), 25, minimum=1, maximum=100),
            offset=_parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000),
        )
        payload["retention_days"] = audit_retention_days(CFG)
        return jsonify(payload)
    except AuditScopeError as exc:
        return jsonify({"error": exc.code, "message": exc.message}), exc.status_code
    except Exception as exc:
        return _log_team_exception("activity", exc, session_token=session_token, team_id=team_id, actor=actor)


@teams_bp.route("/session/teams/<team_id>", methods=["PATCH"])
@limiter.limit(_team_write_route_limit, key_func=get_session_id)
def session_teams_update(team_id):
    session_token, error_response = _required_token_session()
    if error_response:
        return error_response
    data, body_error = _json_body()
    if body_error:
        return body_error
    actor = None
    try:
        def _update(conn):
            nonlocal actor
            actor = _actor_membership(conn, team_id, session_token)
            require_capability(actor["role"], Capability.ARCHIVE_TEAM)
            status = str(data.get("status") or "").strip().lower()
            team = storage.update_team_status(conn, team_id, status=status)
            paused = {"watchers": 0, "schedules": 0}
            if status == "archived":
                paused = pause_team_watchers_and_schedules(conn, team_id, reason="team_archived")
            detail = storage.team_detail(conn, team_id, current_session_token=session_token)
            event_type = AuditEventType.TEAM_ARCHIVE if status == "archived" else AuditEventType.TEAM_REACTIVATE
            _record_team_audit(
                event_type,
                session_token=session_token,
                team_id=team_id,
                actor=actor,
                details={
                    "status": team["status"],
                    "to_state": team["status"],
                    "paused_watchers": paused["watchers"],
                    "paused_schedules": paused["schedules"],
                },
                conn=conn,
            )
            return team, detail, paused, status

        team, detail, paused, status = storage.run_team_transaction(_update)
        if status == "archived":
            log.info(
                "TEAM_ARCHIVE_AUTOMATION_PAUSED",
                extra=_team_log_fields(
                    "archive_automation_paused",
                    session_token=session_token,
                    team_id=team_id,
                    actor=actor,
                    team_status=team["status"],
                    paused_watchers=paused["watchers"],
                    paused_schedules=paused["schedules"],
                ),
            )
        _log_team_event(
            "update",
            session_token=session_token,
            team_id=team_id,
            actor=actor,
            team_status=team["status"],
            paused_watchers=paused["watchers"],
            paused_schedules=paused["schedules"],
        )
        return jsonify(detail or {"team": team})
    except Exception as exc:
        return _log_team_exception("update", exc, session_token=session_token, team_id=team_id, actor=actor)


@teams_bp.route("/session/teams/<team_id>/invites", methods=["POST"])
@limiter.limit(_team_write_route_limit, key_func=get_session_id)
def session_teams_invites_create(team_id):
    session_token, error_response = _required_token_session()
    if error_response:
        return error_response
    data, body_error = _json_body()
    if body_error:
        return body_error
    actor = None
    try:
        def _create_invite(conn):
            nonlocal actor
            actor = _actor_membership(conn, team_id, session_token)
            storage.require_active_team(conn, team_id)
            role = str(data.get("role") or "operator").strip()
            if role == "owner":
                require_capability(actor["role"], Capability.MANAGE_OWNERS)
            else:
                require_capability(actor["role"], Capability.MANAGE_INVITES)
            invite = storage.create_team_invite_with_code(
                conn,
                team_id=team_id,
                role=role,
                created_by_member_id=actor["id"],
                expires_at=str(data.get("expires_at") or ""),
                max_uses=int(data.get("max_uses") or 1),
                label=str(data.get("label") or ""),
            )
            _record_team_audit(
                AuditEventType.TEAM_INVITE,
                session_token=session_token,
                team_id=team_id,
                actor=actor,
                details={"target_invite_id": invite["id"], "role": role},
                conn=conn,
            )
            return invite

        invite = storage.run_team_transaction(_create_invite)
        _log_team_event(
            "invite_create",
            session_token=session_token,
            team_id=team_id,
            actor=actor,
            target_invite_id=invite["id"],
        )
        return jsonify({"invite": invite}), 201
    except Exception as exc:
        return _log_team_exception("invite_create", exc, session_token=session_token, team_id=team_id, actor=actor)


@teams_bp.route("/session/teams/<team_id>/invites/<invite_id>", methods=["DELETE"])
@limiter.limit(_team_write_route_limit, key_func=get_session_id)
def session_teams_invites_revoke(team_id, invite_id):
    session_token, error_response = _required_token_session()
    if error_response:
        return error_response
    actor = None
    try:
        def _revoke_invite(conn):
            nonlocal actor
            actor = _actor_membership(conn, team_id, session_token)
            storage.require_active_team(conn, team_id)
            require_capability(actor["role"], Capability.MANAGE_INVITES)
            removed = storage.revoke_team_invite(conn, invite_id)
            if removed:
                _record_team_audit(
                    AuditEventType.TEAM_REVOKE,
                    session_token=session_token,
                    team_id=team_id,
                    actor=actor,
                    details={"target_invite_id": invite_id, "kind": "invite"},
                    conn=conn,
                )
            return removed

        removed = storage.run_team_transaction(_revoke_invite)
        _log_team_event(
            "invite_revoke",
            session_token=session_token,
            team_id=team_id,
            actor=actor,
            target_invite_id=invite_id,
            result="ok" if removed else "not_found",
        )
        return jsonify({"removed": removed})
    except Exception as exc:
        return _log_team_exception(
            "invite_revoke",
            exc,
            session_token=session_token,
            team_id=team_id,
            actor=actor,
            target_invite_id=invite_id,
        )


@teams_bp.route("/session/teams/join", methods=["POST"])
@limiter.limit(_team_write_route_limit, key_func=get_session_id)
def session_teams_join():
    session_token, error_response = _required_token_session()
    if error_response:
        return error_response
    data, body_error = _json_body()
    if body_error:
        return body_error
    try:
        def _join(conn):
            member = storage.redeem_team_invite(
                conn,
                code=str(data.get("code") or ""),
                session_token=session_token,
                display_name=str(data.get("display_name") or ""),
            )
            detail = storage.team_detail(conn, member["team_id"], current_session_token=session_token)
            _record_team_audit(
                AuditEventType.TEAM_JOIN,
                session_token=session_token,
                team_id=member["team_id"],
                actor_member_id=member["id"],
                actor_role=str(member.get("role") or ""),
                actor_display_name=str(member.get("display_name") or ""),
                details={"target_member_id": member["id"], "role": str(member.get("role") or ""), "kind": "invite"},
                conn=conn,
            )
            return member, detail

        member, detail = storage.run_team_transaction(_join)
        _log_team_event(
            "invite_redeem",
            session_token=session_token,
            team_id=member["team_id"],
            actor_member_id=member["id"],
            actor_role=member.get("role", ""),
        )
        return jsonify(detail or {"member": member}), 201
    except Exception as exc:
        return _log_team_exception("invite_redeem", exc, session_token=session_token)


@teams_bp.route("/session/teams/<team_id>/members/<member_id>", methods=["PATCH"])
@limiter.limit(_team_write_route_limit, key_func=get_session_id)
def session_teams_members_update(team_id, member_id):
    session_token, error_response = _required_token_session()
    if error_response:
        return error_response
    data, body_error = _json_body()
    if body_error:
        return body_error
    actor = None
    try:
        def _update_member(conn):
            nonlocal actor
            actor = _actor_membership(conn, team_id, session_token)
            storage.require_active_team(conn, team_id)
            target = storage.get_member(conn, member_id)
            if not target or target["team_id"] != team_id:
                raise TeamNotFound("Team member not found")
            new_role = str(data.get("role") or target["role"]).strip()
            if target["role"] == "owner" or new_role == "owner":
                require_capability(actor["role"], Capability.MANAGE_OWNERS)
            elif actor["id"] != member_id:
                require_capability(actor["role"], Capability.MANAGE_MEMBERS)
            member = storage.update_team_member(
                conn,
                member_id,
                role=new_role if "role" in data else None,
                display_name=str(data.get("display_name")) if "display_name" in data else None,
            )
            if not member:
                raise TeamNotFound("Team member not found")
            if "role" in data and str(target["role"] or "") != str(member["role"] or ""):
                _record_team_audit(
                    AuditEventType.TEAM_ROLE_CHANGE,
                    session_token=session_token,
                    team_id=team_id,
                    actor=actor,
                    details={
                        "target_member_id": member_id,
                        "from_role": str(target["role"] or ""),
                        "to_role": str(member["role"] or ""),
                    },
                    conn=conn,
                )
            return member

        member = storage.run_team_transaction(_update_member)
        _log_team_event(
            "member_update",
            session_token=session_token,
            team_id=team_id,
            actor=actor,
            target_member_id=member_id,
        )
        return jsonify({"member": storage.public_member(member)})
    except Exception as exc:
        return _log_team_exception(
            "member_update",
            exc,
            session_token=session_token,
            team_id=team_id,
            actor=actor,
            target_member_id=member_id,
        )


@teams_bp.route("/session/teams/<team_id>/members/<member_id>", methods=["DELETE"])
@limiter.limit(_team_write_route_limit, key_func=get_session_id)
def session_teams_members_remove(team_id, member_id):
    session_token, error_response = _required_token_session()
    if error_response:
        return error_response
    actor = None
    try:
        def _remove_member(conn):
            nonlocal actor
            actor = _actor_membership(conn, team_id, session_token)
            storage.require_active_team(conn, team_id)
            target = storage.get_member(conn, member_id)
            if not target or target["team_id"] != team_id:
                raise TeamNotFound("Team member not found")
            if target["role"] == "owner":
                require_capability(actor["role"], Capability.MANAGE_OWNERS)
            elif actor["id"] != member_id:
                require_capability(actor["role"], Capability.MANAGE_MEMBERS)
            removed = storage.soft_remove_team_member(conn, member_id)
            if removed:
                _record_team_audit(
                    AuditEventType.TEAM_MEMBER_REMOVE,
                    session_token=session_token,
                    team_id=team_id,
                    actor=actor,
                    details={"target_member_id": member_id, "role": str(target["role"] or "")},
                    conn=conn,
                )
            return removed

        removed = storage.run_team_transaction(_remove_member)
        _log_team_event(
            "member_remove",
            session_token=session_token,
            team_id=team_id,
            actor=actor,
            target_member_id=member_id,
        )
        return jsonify({"removed": removed})
    except Exception as exc:
        return _log_team_exception(
            "member_remove",
            exc,
            session_token=session_token,
            team_id=team_id,
            actor=actor,
            target_member_id=member_id,
        )


@teams_bp.route("/session/teams/<team_id>/leave", methods=["POST"])
@limiter.limit(_team_write_route_limit, key_func=get_session_id)
def session_teams_leave(team_id):
    session_token, error_response = _required_token_session()
    if error_response:
        return error_response
    actor = None
    try:
        def _leave(conn):
            nonlocal actor
            actor = _actor_membership(conn, team_id, session_token)
            removed = storage.soft_remove_team_member(conn, actor["id"])
            if removed:
                _record_team_audit(
                    AuditEventType.TEAM_LEAVE,
                    session_token=session_token,
                    team_id=team_id,
                    actor=actor,
                    details={"target_member_id": actor["id"], "role": str(actor.get("role") or "")},
                    conn=conn,
                )
            return removed

        removed = storage.run_team_transaction(_leave)
        _log_team_event("leave", session_token=session_token, team_id=team_id, actor=actor)
        return jsonify({"removed": removed})
    except Exception as exc:
        return _log_team_exception("leave", exc, session_token=session_token, team_id=team_id, actor=actor)


@teams_bp.route("/session/teams/<team_id>/recovery/rotate", methods=["POST"])
@limiter.limit(_team_write_route_limit, key_func=get_session_id)
def session_teams_recovery_rotate(team_id):
    session_token, error_response = _required_token_session()
    if error_response:
        return error_response
    actor = None
    try:
        def _rotate_recovery(conn):
            nonlocal actor
            actor = _actor_membership(conn, team_id, session_token)
            storage.require_active_team(conn, team_id)
            require_capability(actor["role"], Capability.MANAGE_RECOVERY)
            recovery = storage.rotate_team_recovery_code(
                conn,
                team_id=team_id,
                created_by_member_id=actor["id"],
            )
            _record_team_audit(
                AuditEventType.TEAM_RECOVERY_ROTATE,
                session_token=session_token,
                team_id=team_id,
                actor=actor,
                details={"target_recovery_id": recovery["id"]},
                conn=conn,
            )
            return recovery

        recovery = storage.run_team_transaction(_rotate_recovery)
        _log_team_event(
            "recovery_rotate",
            session_token=session_token,
            team_id=team_id,
            actor=actor,
            target_recovery_id=recovery["id"],
        )
        return jsonify({"recovery_code": recovery["code"], "recovery": recovery})
    except Exception as exc:
        return _log_team_exception(
            "recovery_rotate",
            exc,
            session_token=session_token,
            team_id=team_id,
            actor=actor,
        )


@teams_bp.route("/session/teams/recovery/redeem", methods=["POST"])
@limiter.limit(_team_write_route_limit, key_func=get_session_id)
def session_teams_recovery_redeem():
    session_token, error_response = _required_token_session()
    if error_response:
        return error_response
    data, body_error = _json_body()
    if body_error:
        return body_error
    try:
        def _redeem_recovery(conn):
            member = storage.redeem_team_recovery_code(
                conn,
                code=str(data.get("code") or ""),
                session_token=session_token,
                display_name=str(data.get("display_name") or ""),
            )
            detail = storage.team_detail(conn, member["team_id"], current_session_token=session_token)
            _record_team_audit(
                AuditEventType.TEAM_RECOVERY_REDEEM,
                session_token=session_token,
                team_id=member["team_id"],
                actor_member_id=member["id"],
                actor_role=str(member.get("role") or ""),
                actor_display_name=str(member.get("display_name") or ""),
                details={
                    "target_member_id": member["id"],
                    "role": str(member.get("role") or ""),
                    "kind": "recovery",
                },
                conn=conn,
            )
            return member, detail

        member, detail = storage.run_team_transaction(_redeem_recovery)
        _log_team_event(
            "recovery_redeem",
            session_token=session_token,
            team_id=member["team_id"],
            actor_member_id=member["id"],
            actor_role=member.get("role", ""),
        )
        return jsonify(detail or {"member": member})
    except Exception as exc:
        return _log_team_exception("recovery_redeem", exc, session_token=session_token)
