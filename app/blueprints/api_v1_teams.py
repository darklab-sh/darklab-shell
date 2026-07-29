# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 team management routes."""

from __future__ import annotations

from flask import jsonify

from blueprints import api_v1 as api_routes


@api_routes.api_v1_bp.route("/teams", methods=["GET"])
@api_routes.limiter.limit(api_routes._api_team_read_route_limit, key_func=api_routes._api_team_rate_limit_key)
@api_routes.require_api_auth
def api_teams_list():
    session_id = api_routes._require_session_id()
    return jsonify({"teams": api_routes.team_api.list_teams_for_api(session_id)})


@api_routes.api_v1_bp.route("/teams", methods=["POST"])
@api_routes.limiter.limit(api_routes._api_team_write_route_limit, key_func=api_routes._api_team_rate_limit_key)
@api_routes.require_api_auth
def api_teams_create():
    session_id = api_routes._require_session_id()
    data = api_routes._json_body()
    try:
        team, recovery, detail = api_routes.team_api.create_team_for_api(
            session_id,
            name=str(data.get("name") or ""),
            slug=str(data.get("slug") or ""),
            display_name=str(data.get("display_name") or ""),
            audit_fields=api_routes._api_actor_audit_fields(session_id),
        )
        api_routes._log_api_team_event(
            "create",
            session_token=session_id,
            team_id=team["id"],
            actor_member_id=team.get("creator_member_id", ""),
            actor_role="owner",
        )
        return jsonify({"team": (detail or {}).get("team", {}), "recovery_code": recovery["code"]}), 201
    except Exception as exc:
        return api_routes._log_api_team_exception("create", exc, session_token=session_id)


@api_routes.api_v1_bp.route("/teams/<team_id>", methods=["GET"])
@api_routes.limiter.limit(api_routes._api_team_read_route_limit, key_func=api_routes._api_team_rate_limit_key)
@api_routes.require_api_auth
def api_teams_detail(team_id: str):
    session_id = api_routes._require_session_id()
    actor = None
    try:
        actor, detail = api_routes.team_api.team_detail_for_api(team_id, session_id)
        return jsonify(detail)
    except Exception as exc:
        return api_routes._log_api_team_exception("detail", exc, session_token=session_id, team_id=team_id, actor=actor)


@api_routes.api_v1_bp.route("/teams/<team_id>", methods=["PATCH"])
@api_routes.limiter.limit(api_routes._api_team_write_route_limit, key_func=api_routes._api_team_rate_limit_key)
@api_routes.require_api_auth
def api_teams_update(team_id: str):
    session_id = api_routes._require_session_id()
    data = api_routes._json_body()
    actor = None
    try:
        actor = api_routes.team_api.team_member_for_api(team_id, session_id)
        api_routes.require_capability(actor["role"], api_routes.Capability.ARCHIVE_TEAM)
        status = str(data.get("status") or "").strip().lower()
        team, detail, paused = api_routes.team_api.update_team_for_api(
            team_id,
            session_id,
            status=status,
            actor=actor,
            audit_fields=api_routes._api_actor_audit_fields(session_id, team_id=team_id, actor=actor),
            pause_automation=api_routes.pause_team_watchers_and_schedules,
        )
        if status == "archived":
            api_routes.log.info(
                "TEAM_ARCHIVE_AUTOMATION_PAUSED",
                extra=api_routes._api_team_log_fields(
                    "archive_automation_paused",
                    session_token=session_id,
                    team_id=team_id,
                    actor=actor,
                    team_status=team["status"],
                    paused_watchers=paused["watchers"],
                    paused_schedules=paused["schedules"],
                ),
            )
        api_routes._log_api_team_event(
            "update",
            session_token=session_id,
            team_id=team_id,
            actor=actor,
            team_status=team["status"],
            paused_watchers=paused["watchers"],
            paused_schedules=paused["schedules"],
        )
        return jsonify(detail or {"team": team})
    except Exception as exc:
        return api_routes._log_api_team_exception("update", exc, session_token=session_id, team_id=team_id, actor=actor)


@api_routes.api_v1_bp.route("/teams/<team_id>/invites", methods=["POST"])
@api_routes.limiter.limit(api_routes._api_team_write_route_limit, key_func=api_routes._api_team_rate_limit_key)
@api_routes.require_api_auth
def api_teams_invites_create(team_id: str):
    session_id = api_routes._require_session_id()
    data = api_routes._json_body()
    actor = None
    try:
        actor = api_routes.team_api.team_member_for_api(team_id, session_id)
        role = str(data.get("role") or "operator").strip()
        api_routes.require_capability(
            actor["role"],
            api_routes.Capability.MANAGE_OWNERS if role == "owner" else api_routes.Capability.MANAGE_INVITES,
        )
        invite = api_routes.team_api.create_team_invite_for_api(
            team_id,
            actor=actor,
            role=role,
            expires_at=str(data.get("expires_at") or ""),
            max_uses=int(data.get("max_uses") or 1),
            label=str(data.get("label") or ""),
            audit_fields=api_routes._api_actor_audit_fields(session_id, team_id=team_id, actor=actor),
        )
        api_routes._log_api_team_event(
            "invite_create",
            session_token=session_id,
            team_id=team_id,
            actor=actor,
            target_invite_id=invite["id"],
        )
        return jsonify({"invite": invite}), 201
    except Exception as exc:
        return api_routes._log_api_team_exception(
            "invite_create",
            exc,
            session_token=session_id,
            team_id=team_id,
            actor=actor,
        )


@api_routes.api_v1_bp.route("/teams/<team_id>/invites/<invite_id>", methods=["DELETE"])
@api_routes.limiter.limit(api_routes._api_team_write_route_limit, key_func=api_routes._api_team_rate_limit_key)
@api_routes.require_api_auth
def api_teams_invites_revoke(team_id: str, invite_id: str):
    session_id = api_routes._require_session_id()
    actor = None
    try:
        actor = api_routes.team_api.team_member_for_api(team_id, session_id)
        api_routes.require_capability(actor["role"], api_routes.Capability.MANAGE_INVITES)
        removed = api_routes.team_api.revoke_team_invite_for_api(
            team_id,
            invite_id,
            audit_fields=api_routes._api_actor_audit_fields(session_id, team_id=team_id, actor=actor),
        )
        api_routes._log_api_team_event(
            "invite_revoke",
            session_token=session_id,
            team_id=team_id,
            actor=actor,
            target_invite_id=invite_id,
            result="ok" if removed else "not_found",
        )
        return jsonify({"removed": removed})
    except Exception as exc:
        return api_routes._log_api_team_exception(
            "invite_revoke",
            exc,
            session_token=session_id,
            team_id=team_id,
            actor=actor,
            target_invite_id=invite_id,
        )


@api_routes.api_v1_bp.route("/teams/join", methods=["POST"])
@api_routes.limiter.limit(api_routes._api_team_write_route_limit, key_func=api_routes._api_team_rate_limit_key)
@api_routes.require_api_auth
def api_teams_join():
    session_id = api_routes._require_session_id()
    data = api_routes._json_body()
    try:
        member, detail = api_routes.team_api.redeem_team_invite_for_api(
            session_id,
            code=str(data.get("code") or ""),
            display_name=str(data.get("display_name") or ""),
            audit_fields=api_routes._api_actor_audit_fields(session_id),
        )
        api_routes._log_api_team_event(
            "invite_redeem",
            session_token=session_id,
            team_id=member["team_id"],
            actor_member_id=member["id"],
            actor_role=member.get("role", ""),
        )
        return jsonify(detail or {"member": member}), 201
    except Exception as exc:
        return api_routes._log_api_team_exception("invite_redeem", exc, session_token=session_id)


@api_routes.api_v1_bp.route("/teams/<team_id>/members/<member_id>", methods=["PATCH"])
@api_routes.limiter.limit(api_routes._api_team_write_route_limit, key_func=api_routes._api_team_rate_limit_key)
@api_routes.require_api_auth
def api_teams_members_update(team_id: str, member_id: str):
    session_id = api_routes._require_session_id()
    data = api_routes._json_body()
    actor = None
    try:
        actor, target = api_routes.team_api.team_member_and_target_for_api(team_id, session_id, member_id)
        new_role = str(data.get("role") or target["role"]).strip()
        if target["role"] == "owner" or new_role == "owner":
            api_routes.require_capability(actor["role"], api_routes.Capability.MANAGE_OWNERS)
        elif actor["id"] != member_id:
            api_routes.require_capability(actor["role"], api_routes.Capability.MANAGE_MEMBERS)
        member = api_routes.team_api.update_team_member_for_api(
            team_id,
            member_id,
            target=target,
            role=new_role if "role" in data else None,
            display_name=str(data.get("display_name")) if "display_name" in data else None,
            audit_fields=api_routes._api_actor_audit_fields(session_id, team_id=team_id, actor=actor),
        )
        api_routes._log_api_team_event(
            "member_update",
            session_token=session_id,
            team_id=team_id,
            actor=actor,
            target_member_id=member_id,
        )
        return jsonify({"member": member})
    except Exception as exc:
        return api_routes._log_api_team_exception(
            "member_update",
            exc,
            session_token=session_id,
            team_id=team_id,
            actor=actor,
            target_member_id=member_id,
        )


@api_routes.api_v1_bp.route("/teams/<team_id>/members/<member_id>", methods=["DELETE"])
@api_routes.limiter.limit(api_routes._api_team_write_route_limit, key_func=api_routes._api_team_rate_limit_key)
@api_routes.require_api_auth
def api_teams_members_remove(team_id: str, member_id: str):
    session_id = api_routes._require_session_id()
    actor = None
    try:
        actor, target = api_routes.team_api.team_member_and_target_for_api(team_id, session_id, member_id)
        if target["role"] == "owner":
            api_routes.require_capability(actor["role"], api_routes.Capability.MANAGE_OWNERS)
        elif actor["id"] != member_id:
            api_routes.require_capability(actor["role"], api_routes.Capability.MANAGE_MEMBERS)
        removed = api_routes.team_api.remove_team_member_for_api(
            team_id,
            member_id,
            target=target,
            audit_fields=api_routes._api_actor_audit_fields(session_id, team_id=team_id, actor=actor),
        )
        api_routes._log_api_team_event(
            "member_remove",
            session_token=session_id,
            team_id=team_id,
            actor=actor,
            target_member_id=member_id,
        )
        return jsonify({"removed": removed})
    except Exception as exc:
        return api_routes._log_api_team_exception(
            "member_remove",
            exc,
            session_token=session_id,
            team_id=team_id,
            actor=actor,
            target_member_id=member_id,
        )


@api_routes.api_v1_bp.route("/teams/<team_id>/leave", methods=["POST"])
@api_routes.limiter.limit(api_routes._api_team_write_route_limit, key_func=api_routes._api_team_rate_limit_key)
@api_routes.require_api_auth
def api_teams_leave(team_id: str):
    session_id = api_routes._require_session_id()
    actor = None
    try:
        actor = api_routes.team_api.team_member_for_api(team_id, session_id)
        removed = api_routes.team_api.leave_team_for_api(
            team_id,
            actor=actor,
            audit_fields=api_routes._api_actor_audit_fields(session_id, team_id=team_id, actor=actor),
        )
        api_routes._log_api_team_event("leave", session_token=session_id, team_id=team_id, actor=actor)
        return jsonify({"removed": removed})
    except Exception as exc:
        return api_routes._log_api_team_exception("leave", exc, session_token=session_id, team_id=team_id, actor=actor)


@api_routes.api_v1_bp.route("/teams/<team_id>/recovery/rotate", methods=["POST"])
@api_routes.limiter.limit(api_routes._api_team_write_route_limit, key_func=api_routes._api_team_rate_limit_key)
@api_routes.require_api_auth
def api_teams_recovery_rotate(team_id: str):
    session_id = api_routes._require_session_id()
    actor = None
    try:
        actor = api_routes.team_api.team_member_for_api(team_id, session_id)
        api_routes.require_capability(actor["role"], api_routes.Capability.MANAGE_RECOVERY)
        recovery = api_routes.team_api.rotate_team_recovery_for_api(
            team_id,
            actor=actor,
            audit_fields=api_routes._api_actor_audit_fields(session_id, team_id=team_id, actor=actor),
        )
        api_routes._log_api_team_event(
            "recovery_rotate",
            session_token=session_id,
            team_id=team_id,
            actor=actor,
            target_recovery_id=recovery["id"],
        )
        return jsonify({"recovery_code": recovery["code"], "recovery": recovery})
    except Exception as exc:
        return api_routes._log_api_team_exception(
            "recovery_rotate",
            exc,
            session_token=session_id,
            team_id=team_id,
            actor=actor,
        )


@api_routes.api_v1_bp.route("/teams/recovery/redeem", methods=["POST"])
@api_routes.limiter.limit(api_routes._api_team_write_route_limit, key_func=api_routes._api_team_rate_limit_key)
@api_routes.require_api_auth
def api_teams_recovery_redeem():
    session_id = api_routes._require_session_id()
    data = api_routes._json_body()
    try:
        member, detail = api_routes.team_api.redeem_team_recovery_for_api(
            session_id,
            code=str(data.get("code") or ""),
            display_name=str(data.get("display_name") or ""),
            audit_fields=api_routes._api_actor_audit_fields(session_id),
        )
        api_routes._log_api_team_event(
            "recovery_redeem",
            session_token=session_id,
            team_id=member["team_id"],
            actor_member_id=member["id"],
            actor_role=member.get("role", ""),
        )
        return jsonify(detail or {"member": member})
    except Exception as exc:
        return api_routes._log_api_team_exception("recovery_redeem", exc, session_token=session_id)
