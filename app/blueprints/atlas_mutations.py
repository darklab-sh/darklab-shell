# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Atlas mutation, cleanup, and relationship routes."""

from __future__ import annotations

from flask import jsonify, request

from blueprints import atlas as atlas_routes
from services.atlas.cleanup import (
    atlas_entity_delete_preview,
    atlas_finding_delete_preview,
    atlas_run_cleanup_preview,
    delete_atlas_cleanup_preview,
    delete_atlas_entities,
    delete_atlas_findings,
    detach_atlas_run_sources,
    public_cleanup_preview,
)
from services.atlas.intel_bridge import refresh_entity_intel
from services.atlas.lookup import (
    entity_exists_in_scope,
    entity_ids_in_session,
    finding_exists_in_scope,
    finding_ids_in_session,
    run_belongs_to_session,
    update_entities_suppression,
    update_entity_suppression,
    update_finding_review_states,
    update_finding_suppression,
    update_findings_suppression,
)
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.audit.context import route_audit_fields
from services.projects.contracts import MAX_BULK_RUN_ACTION_ITEMS, ProjectWorkspaceError
from services.projects.links import link_project_entity, unlink_project_entity
from services.teams.capabilities import Capability


@atlas_routes.atlas_bp.route("/atlas/runs/<run_id>/cleanup-preview")
def atlas_run_cleanup_preview_route(run_id):
    session_id = atlas_routes.get_session_id()

    def _preview(conn):
        if not run_belongs_to_session(conn, session_id, run_id):
            return None
        return atlas_run_cleanup_preview(conn, session_id, [run_id])

    preview = atlas_routes.run_atlas_read(_preview)
    if preview is None:
        return jsonify({"error": "run not found"}), 404
    return jsonify({"ok": True, "cleanup": public_cleanup_preview(preview)})


@atlas_routes.atlas_bp.route("/atlas/runs/<run_id>/cleanup", methods=["POST"])
@atlas_routes.limiter.limit(atlas_routes._atlas_write_limit)
def atlas_run_cleanup(run_id):
    session_id = atlas_routes.get_session_id()
    data = request.get_json(silent=True) or {}
    include_curated = bool(data.get("include_curated")) if isinstance(data, dict) else False

    def _cleanup(conn):
        if not run_belongs_to_session(conn, session_id, run_id):
            return None
        cleanup = detach_atlas_run_sources(conn, session_id, [run_id], include_curated=include_curated)
        return cleanup

    cleanup = atlas_routes.run_atlas_transaction(_cleanup)
    if cleanup is None:
        return jsonify({"error": "run not found"}), 404
    atlas_routes.log.info("ATLAS_RUN_CLEANED", extra={
        "ip": atlas_routes.get_client_ip(),
        "session": atlas_routes.get_log_session_id(session_id),
        "run_id": run_id,
        "include_curated": include_curated,
        "detached_entities": cleanup.get("detached_entities", 0),
        "detached_findings": cleanup.get("detached_findings", 0),
        "deleted_entities": cleanup.get("deleted_entities", 0),
        "deleted_findings": cleanup.get("deleted_findings", 0),
    })
    return jsonify({"ok": True, "cleanup": cleanup})


@atlas_routes.atlas_bp.route("/atlas/findings/review", methods=["POST"])
@atlas_routes.limiter.limit(atlas_routes._atlas_write_limit)
def atlas_findings_bulk_review_update():
    session_id = atlas_routes.get_session_id()
    owner_scope, scope_response = atlas_routes._atlas_request_scope_response(session_id, Capability.TRIAGE_FINDINGS)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    data = request.get_json(silent=True) or {}
    finding_ids = atlas_routes._normalize_finding_ids(data.get("finding_ids"))
    review_state = atlas_routes._normalize_review_state(data.get("review_state"))
    if not finding_ids:
        return jsonify({"error": "finding_ids are required"}), 400
    if len(finding_ids) > MAX_BULK_RUN_ACTION_ITEMS:
        return jsonify({"error": "too_many", "limit": MAX_BULK_RUN_ACTION_ITEMS}), 400
    if not review_state:
        return jsonify({"error": "review_state is invalid"}), 400

    def _update_review(conn):
        found_ids: set[str] = set()
        for finding_id in finding_ids:
            if finding_exists_in_scope(conn, session_id, finding_id, team_id=owner_scope.team_id):
                found_ids.add(finding_id)
        if found_ids:
            update_finding_review_states(
                conn,
                found_ids,
                review_state=review_state,
                updated_at=atlas_routes._now_for_review(),
            )
        return found_ids

    found_ids = atlas_routes.run_atlas_transaction(_update_review)
    results = [
        {"finding_id": finding_id, "status": "updated" if finding_id in found_ids else "not_found"}
        for finding_id in finding_ids
    ]
    atlas_routes.log.info("ATLAS_FINDINGS_BULK_REVIEW_UPDATED", extra={
        "ip": atlas_routes.get_client_ip(),
        "session": atlas_routes.get_log_session_id(session_id),
        "review_state": review_state,
        "updated": len(found_ids),
        "not_found": len(finding_ids) - len(found_ids),
    })
    return jsonify({
        "ok": True,
        "review_state": review_state,
        "counts": {
            "updated": len(found_ids),
            "not_found": len(finding_ids) - len(found_ids),
        },
        "results": results,
    })


@atlas_routes.atlas_bp.route("/atlas/entities/<entity_id>/suppression", methods=["PUT"])
@atlas_routes.limiter.limit(atlas_routes._atlas_write_limit)
def atlas_entity_suppression_update(entity_id):
    session_id = atlas_routes.get_session_id()
    owner_scope, scope_response = atlas_routes._atlas_request_scope_response(session_id, Capability.TRIAGE_FINDINGS)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    suppressed, reason = atlas_routes._suppression_payload(request.get_json(silent=True) or {})

    def _update_entity_suppression(conn):
        if not entity_exists_in_scope(conn, session_id, entity_id, team_id=owner_scope.team_id):
            return False
        update_entity_suppression(
            conn,
            entity_id,
            suppressed=suppressed,
            reason=reason,
            suppressed_at=atlas_routes._suppression_timestamp(suppressed),
        )
        record_event(
            AuditEventType.ENTITY_SUPPRESS,
            target_id=entity_id,
            details={
                "entity_id": entity_id,
                "suppressed": suppressed,
                "reason": reason,
                "source": "atlas",
            },
            conn=conn,
            **route_audit_fields(session_id, request, owner_scope),
        )
        return True

    if not atlas_routes.run_atlas_transaction(_update_entity_suppression):
        return jsonify({"error": "entity not found"}), 404
    atlas_routes.log.info("ATLAS_ENTITY_SUPPRESSION_UPDATED", extra={
        "ip": atlas_routes.get_client_ip(),
        "session": atlas_routes.get_log_session_id(session_id),
        "entity_id": entity_id,
        "suppressed": suppressed,
        "reason": reason,
    })
    return jsonify({"ok": True, "entity_id": entity_id, "suppressed": suppressed})


@atlas_routes.atlas_bp.route("/atlas/entities/suppression", methods=["POST"])
@atlas_routes.limiter.limit(atlas_routes._atlas_write_limit)
def atlas_entities_bulk_suppression_update():
    session_id = atlas_routes.get_session_id()
    owner_scope, scope_response = atlas_routes._atlas_request_scope_response(session_id, Capability.TRIAGE_FINDINGS)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    data = request.get_json(silent=True) or {}
    entity_ids = atlas_routes._normalize_entity_ids(data.get("entity_ids"))
    suppressed, reason = atlas_routes._suppression_payload(data)
    if not entity_ids:
        return jsonify({"error": "entity_ids are required"}), 400
    if len(entity_ids) > MAX_BULK_RUN_ACTION_ITEMS:
        return jsonify({"error": "too_many", "limit": MAX_BULK_RUN_ACTION_ITEMS}), 400

    def _bulk_entity_suppression(conn):
        found_ids = {
            item_id
            for item_id in entity_ids
            if entity_exists_in_scope(conn, session_id, item_id, team_id=owner_scope.team_id)
        }
        if found_ids:
            update_entities_suppression(
                conn,
                found_ids,
                suppressed=suppressed,
                reason=reason,
                suppressed_at=atlas_routes._suppression_timestamp(suppressed),
            )
            record_event(
                AuditEventType.ENTITY_SUPPRESS,
                target_id="",
                details={
                    "entity_ids": sorted(found_ids),
                    "updated_count": len(found_ids),
                    "suppressed": suppressed,
                    "reason": reason,
                    "source": "atlas_bulk",
                },
                conn=conn,
                **route_audit_fields(session_id, request, owner_scope),
            )
        return found_ids

    found_ids = atlas_routes.run_atlas_transaction(_bulk_entity_suppression)
    results = [
        {"entity_id": item_id, "status": "updated" if item_id in found_ids else "not_found"}
        for item_id in entity_ids
    ]
    atlas_routes.log.info("ATLAS_ENTITY_SUPPRESSION_UPDATED", extra={
        "ip": atlas_routes.get_client_ip(),
        "session": atlas_routes.get_log_session_id(session_id),
        "count": len(found_ids),
        "not_found": len(entity_ids) - len(found_ids),
        "suppressed": suppressed,
        "bulk": True,
    })
    return jsonify({
        "ok": True,
        "suppressed": suppressed,
        "counts": {"updated": len(found_ids), "not_found": len(entity_ids) - len(found_ids)},
        "results": results,
    })


@atlas_routes.atlas_bp.route("/atlas/entities/bulk-delete", methods=["POST"])
@atlas_routes.limiter.limit(atlas_routes._atlas_write_limit)
def atlas_entities_bulk_delete():
    session_id = atlas_routes.get_session_id()
    data = request.get_json(silent=True) or {}
    entity_ids = atlas_routes._normalize_entity_ids(data.get("entity_ids"))
    if not entity_ids:
        return jsonify({"error": "entity_ids are required"}), 400
    if len(entity_ids) > MAX_BULK_RUN_ACTION_ITEMS:
        return jsonify({"error": "too_many", "limit": MAX_BULK_RUN_ACTION_ITEMS}), 400

    def _bulk_delete_entities(conn):
        found_ids = entity_ids_in_session(conn, session_id, entity_ids)
        deleted = delete_atlas_entities(conn, session_id, entity_ids)
        if deleted.get("entities"):
            record_event(
                AuditEventType.ENTITY_DELETE,
                target_id="",
                details={
                    "entity_ids": sorted(found_ids),
                    "deleted_count": int(deleted.get("entities") or 0),
                    "finding_count": int(deleted.get("findings") or 0),
                    "source": "atlas_bulk",
                },
                conn=conn,
                **route_audit_fields(session_id, request),
            )
        return found_ids, deleted

    found_ids, deleted = atlas_routes.run_atlas_transaction(_bulk_delete_entities)
    results = [
        {"entity_id": entity_id, "status": "deleted" if entity_id in found_ids else "not_found"}
        for entity_id in entity_ids
    ]
    atlas_routes.log.info("ATLAS_ENTITIES_BULK_DELETED", extra={
        "ip": atlas_routes.get_client_ip(),
        "session": atlas_routes.get_log_session_id(session_id),
        "deleted_entities": deleted.get("entities", 0),
        "deleted_findings": deleted.get("findings", 0),
        "not_found": len(entity_ids) - len(found_ids),
    })
    return jsonify({
        "ok": True,
        "counts": {
            "deleted": int(deleted.get("entities") or 0),
            "findings_deleted": int(deleted.get("findings") or 0),
            "not_found": len(entity_ids) - len(found_ids),
        },
        "results": results,
    })


@atlas_routes.atlas_bp.route("/atlas/entities/<entity_id>/delete-preview")
def atlas_entity_delete_preview_route(entity_id):
    session_id = atlas_routes.get_session_id()
    preview = atlas_routes.run_atlas_read(lambda conn: atlas_entity_delete_preview(conn, session_id, entity_id))
    if preview is None:
        return jsonify({"error": "entity not found"}), 404
    return jsonify({"ok": True, "preview": preview})


@atlas_routes.atlas_bp.route("/atlas/entities/<entity_id>", methods=["DELETE"])
@atlas_routes.limiter.limit(atlas_routes._atlas_write_limit)
def atlas_entity_delete(entity_id):
    session_id = atlas_routes.get_session_id()
    data = request.get_json(silent=True) or {}
    prune_source_run = bool(data.get("prune_source_run")) if isinstance(data, dict) else False
    prune_curated_source_run = bool(data.get("prune_curated_source_run")) if isinstance(data, dict) else False

    def _delete_entity(conn):
        preview = atlas_entity_delete_preview(conn, session_id, entity_id)
        if preview is None:
            return None
        sibling_cleanup = None
        source_run_id = str(preview.get("source_run_id") or "")
        if prune_source_run:
            sibling_cleanup = atlas_run_cleanup_preview(
                conn,
                session_id,
                [source_run_id],
                exclude_entity_ids=[entity_id],
                exclude_finding_ids=preview.get("attached_finding_ids") or [],
                include_curated=prune_curated_source_run,
            )
        deleted = delete_atlas_entities(conn, session_id, [entity_id])
        cleanup = delete_atlas_cleanup_preview(conn, session_id, sibling_cleanup or {})
        deleted_count = int(deleted.get("entities") or 0) + int(cleanup.get("entities") or 0)
        finding_count = int(deleted.get("findings") or 0) + int(cleanup.get("findings") or 0)
        if deleted_count:
            record_event(
                AuditEventType.ENTITY_DELETE,
                target_id=entity_id,
                details={
                    "entity_id": entity_id,
                    "deleted_count": deleted_count,
                    "finding_count": finding_count,
                    "run_id": source_run_id,
                    "source": "atlas",
                },
                conn=conn,
                **route_audit_fields(session_id, request),
            )
        return preview, source_run_id, deleted, cleanup

    delete_result = atlas_routes.run_atlas_transaction(_delete_entity)
    if delete_result is None:
        return jsonify({"error": "entity not found"}), 404
    preview, source_run_id, deleted, cleanup = delete_result
    atlas_routes.log.info("ATLAS_ENTITY_DELETED", extra={
        "ip": atlas_routes.get_client_ip(),
        "session": atlas_routes.get_log_session_id(session_id),
        "entity_id": entity_id,
        "source_run_cleanup": bool(prune_source_run and source_run_id),
        "deleted_entities": deleted.get("entities", 0) + cleanup.get("entities", 0),
        "deleted_findings": deleted.get("findings", 0) + cleanup.get("findings", 0),
    })
    return jsonify({"ok": True, "deleted": deleted, "sibling_cleanup": cleanup})


@atlas_routes.atlas_bp.route("/atlas/findings/bulk-delete", methods=["POST"])
@atlas_routes.limiter.limit(atlas_routes._atlas_write_limit)
def atlas_findings_bulk_delete():
    session_id = atlas_routes.get_session_id()
    data = request.get_json(silent=True) or {}
    finding_ids = atlas_routes._normalize_finding_ids(data.get("finding_ids"))
    if not finding_ids:
        return jsonify({"error": "finding_ids are required"}), 400
    if len(finding_ids) > MAX_BULK_RUN_ACTION_ITEMS:
        return jsonify({"error": "too_many", "limit": MAX_BULK_RUN_ACTION_ITEMS}), 400

    def _bulk_delete_findings(conn):
        found_ids = finding_ids_in_session(conn, session_id, finding_ids)
        deleted_findings = delete_atlas_findings(conn, session_id, finding_ids)
        if deleted_findings:
            record_event(
                AuditEventType.FINDING_DELETE,
                target_id="",
                details={
                    "finding_ids": sorted(found_ids),
                    "deleted_count": deleted_findings,
                    "source": "atlas_bulk",
                },
                conn=conn,
                **route_audit_fields(session_id, request),
            )
        return found_ids, deleted_findings

    found_ids, deleted_findings = atlas_routes.run_atlas_transaction(_bulk_delete_findings)
    results = [
        {"finding_id": finding_id, "status": "deleted" if finding_id in found_ids else "not_found"}
        for finding_id in finding_ids
    ]
    atlas_routes.log.info("ATLAS_FINDINGS_BULK_DELETED", extra={
        "ip": atlas_routes.get_client_ip(),
        "session": atlas_routes.get_log_session_id(session_id),
        "deleted_findings": deleted_findings,
        "not_found": len(finding_ids) - len(found_ids),
    })
    return jsonify({
        "ok": True,
        "counts": {
            "deleted": deleted_findings,
            "not_found": len(finding_ids) - len(found_ids),
        },
        "results": results,
    })


@atlas_routes.atlas_bp.route("/atlas/findings/<finding_id>/suppression", methods=["PUT"])
@atlas_routes.limiter.limit(atlas_routes._atlas_write_limit)
def atlas_finding_suppression_update(finding_id):
    session_id = atlas_routes.get_session_id()
    owner_scope, scope_response = atlas_routes._atlas_request_scope_response(session_id, Capability.TRIAGE_FINDINGS)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    suppressed, reason = atlas_routes._suppression_payload(request.get_json(silent=True) or {})

    def _update_finding_suppression(conn):
        if not finding_exists_in_scope(conn, session_id, finding_id, team_id=owner_scope.team_id):
            return False
        update_finding_suppression(
            conn,
            finding_id,
            suppressed=suppressed,
            reason=reason,
            suppressed_at=atlas_routes._suppression_timestamp(suppressed),
        )
        record_event(
            AuditEventType.FINDING_SUPPRESS,
            target_id=finding_id,
            details={
                "finding_id": finding_id,
                "suppressed": suppressed,
                "reason": reason,
            },
            conn=conn,
            **route_audit_fields(session_id, request, owner_scope),
        )
        return True

    if not atlas_routes.run_atlas_transaction(_update_finding_suppression):
        return jsonify({"error": "finding not found"}), 404
    atlas_routes.log.info("ATLAS_FINDING_SUPPRESSION_UPDATED", extra={
        "ip": atlas_routes.get_client_ip(),
        "session": atlas_routes.get_log_session_id(session_id),
        "finding_id": finding_id,
        "suppressed": suppressed,
        "reason": reason,
    })
    return jsonify({"ok": True, "finding_id": finding_id, "suppressed": suppressed})


@atlas_routes.atlas_bp.route("/atlas/findings/suppression", methods=["POST"])
@atlas_routes.limiter.limit(atlas_routes._atlas_write_limit)
def atlas_findings_bulk_suppression_update():
    session_id = atlas_routes.get_session_id()
    owner_scope, scope_response = atlas_routes._atlas_request_scope_response(session_id, Capability.TRIAGE_FINDINGS)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    data = request.get_json(silent=True) or {}
    finding_ids = atlas_routes._normalize_finding_ids(data.get("finding_ids"))
    suppressed, reason = atlas_routes._suppression_payload(data)
    if not finding_ids:
        return jsonify({"error": "finding_ids are required"}), 400
    if len(finding_ids) > MAX_BULK_RUN_ACTION_ITEMS:
        return jsonify({"error": "too_many", "limit": MAX_BULK_RUN_ACTION_ITEMS}), 400

    def _bulk_finding_suppression(conn):
        found_ids = {
            item_id
            for item_id in finding_ids
            if finding_exists_in_scope(conn, session_id, item_id, team_id=owner_scope.team_id)
        }
        if found_ids:
            update_findings_suppression(
                conn,
                found_ids,
                suppressed=suppressed,
                reason=reason,
                suppressed_at=atlas_routes._suppression_timestamp(suppressed),
            )
            record_event(
                AuditEventType.FINDING_SUPPRESS,
                target_id="",
                details={
                    "finding_ids": sorted(found_ids),
                    "updated_count": len(found_ids),
                    "suppressed": suppressed,
                    "reason": reason,
                },
                conn=conn,
                **route_audit_fields(session_id, request, owner_scope),
            )
        return found_ids

    found_ids = atlas_routes.run_atlas_transaction(_bulk_finding_suppression)
    results = [
        {"finding_id": item_id, "status": "updated" if item_id in found_ids else "not_found"}
        for item_id in finding_ids
    ]
    atlas_routes.log.info("ATLAS_FINDING_SUPPRESSION_UPDATED", extra={
        "ip": atlas_routes.get_client_ip(),
        "session": atlas_routes.get_log_session_id(session_id),
        "count": len(found_ids),
        "not_found": len(finding_ids) - len(found_ids),
        "suppressed": suppressed,
        "bulk": True,
    })
    return jsonify({
        "ok": True,
        "suppressed": suppressed,
        "counts": {"updated": len(found_ids), "not_found": len(finding_ids) - len(found_ids)},
        "results": results,
    })


@atlas_routes.atlas_bp.route("/atlas/findings/<finding_id>/delete-preview")
def atlas_finding_delete_preview_route(finding_id):
    session_id = atlas_routes.get_session_id()
    preview = atlas_routes.run_atlas_read(lambda conn: atlas_finding_delete_preview(conn, session_id, finding_id))
    if preview is None:
        return jsonify({"error": "finding not found"}), 404
    return jsonify({"ok": True, "preview": preview})


@atlas_routes.atlas_bp.route("/atlas/findings/<finding_id>", methods=["DELETE"])
@atlas_routes.limiter.limit(atlas_routes._atlas_write_limit)
def atlas_finding_delete(finding_id):
    session_id = atlas_routes.get_session_id()
    data = request.get_json(silent=True) or {}
    prune_source_run = bool(data.get("prune_source_run")) if isinstance(data, dict) else False
    prune_curated_source_run = bool(data.get("prune_curated_source_run")) if isinstance(data, dict) else False

    def _delete_finding(conn):
        preview = atlas_finding_delete_preview(conn, session_id, finding_id)
        if preview is None:
            return None
        sibling_cleanup = None
        source_run_id = str(preview.get("source_run_id") or "")
        if prune_source_run and source_run_id:
            sibling_cleanup = atlas_run_cleanup_preview(
                conn,
                session_id,
                [source_run_id],
                exclude_finding_ids=[finding_id],
                include_curated=prune_curated_source_run,
            )
        deleted_findings = delete_atlas_findings(conn, session_id, [finding_id])
        cleanup = delete_atlas_cleanup_preview(conn, session_id, sibling_cleanup or {})
        if deleted_findings:
            record_event(
                AuditEventType.FINDING_DELETE,
                target_id=finding_id,
                details={
                    "finding_id": finding_id,
                    "deleted_count": deleted_findings + int(cleanup.get("findings") or 0),
                    "finding_count": deleted_findings + int(cleanup.get("findings") or 0),
                    "source": "atlas",
                    "run_id": source_run_id,
                },
                conn=conn,
                **route_audit_fields(session_id, request),
            )
        return source_run_id, deleted_findings, cleanup

    delete_result = atlas_routes.run_atlas_transaction(_delete_finding)
    if delete_result is None:
        return jsonify({"error": "finding not found"}), 404
    source_run_id, deleted_findings, cleanup = delete_result
    atlas_routes.log.info("ATLAS_FINDING_DELETED", extra={
        "ip": atlas_routes.get_client_ip(),
        "session": atlas_routes.get_log_session_id(session_id),
        "finding_id": finding_id,
        "source_run_cleanup": bool(prune_source_run and source_run_id),
        "deleted_findings": deleted_findings + cleanup.get("findings", 0),
        "deleted_entities": cleanup.get("entities", 0),
    })
    return jsonify({
        "ok": True,
        "deleted": {"findings": deleted_findings},
        "sibling_cleanup": cleanup,
    })


@atlas_routes.atlas_bp.route("/atlas/entities/<entity_id>/refresh_intel", methods=["POST"])
@atlas_routes.limiter.limit(atlas_routes._atlas_write_limit)
def atlas_entity_intel_refresh(entity_id):
    session_id = atlas_routes.get_session_id()
    owner_scope, scope_response = atlas_routes._atlas_request_scope_response(session_id, Capability.TRIAGE_FINDINGS)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    try:
        result = refresh_entity_intel(session_id, entity_id, team_id=owner_scope.team_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if result is None:
        return jsonify({"error": "entity not found"}), 404
    atlas_routes.log.info("ATLAS_INTEL_REFRESH", extra={
        "ip": atlas_routes.get_client_ip(),
        "session": atlas_routes.get_log_session_id(session_id),
        "entity_id": entity_id,
        "success_count": result["success_count"],
    })
    return jsonify({"ok": True, "refresh": result})


@atlas_routes.atlas_bp.route("/atlas/entities/<entity_id>/project_links", methods=["POST"])
@atlas_routes.limiter.limit(atlas_routes._atlas_write_limit)
def atlas_entity_project_link_create(entity_id):
    session_id = atlas_routes.get_session_id()
    owner_scope, scope_response = atlas_routes._atlas_request_scope_response(session_id, Capability.MUTATE_PROJECTS)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    data = request.get_json(silent=True) or {}
    project_id = str(data.get("project_id") or "").strip()
    if not project_id:
        return jsonify({"error": "project_id is required"}), 400
    try:
        link = link_project_entity(
            session_id,
            project_id,
            {
                "entity_type": "atlas_entity",
                "entity_id": entity_id,
                "source": "manual",
            },
            team_id=owner_scope.team_id,
        )
    except ProjectWorkspaceError as exc:
        return jsonify({"error": str(exc)}), 400
    if link is None:
        return jsonify({"error": "project not found"}), 404
    atlas_routes.log.info("ATLAS_PROJECT_LINK_ADDED", extra={
        "ip": atlas_routes.get_client_ip(),
        "session": atlas_routes.get_log_session_id(session_id),
        "project_id": project_id,
        "entity_id": entity_id,
    })
    return jsonify({"ok": True, "link": link}), 201


@atlas_routes.atlas_bp.route("/atlas/entities/<entity_id>/project_links/<project_id>", methods=["DELETE"])
@atlas_routes.limiter.limit(atlas_routes._atlas_write_limit)
def atlas_entity_project_link_delete(entity_id, project_id):
    session_id = atlas_routes.get_session_id()
    owner_scope, scope_response = atlas_routes._atlas_request_scope_response(session_id, Capability.MUTATE_PROJECTS)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    try:
        deleted = unlink_project_entity(session_id, project_id, {
            "entity_type": "atlas_entity",
            "entity_id": entity_id,
        }, team_id=owner_scope.team_id)
    except ProjectWorkspaceError as exc:
        return jsonify({"error": str(exc)}), 400
    if deleted is None:
        return jsonify({"error": "project not found"}), 404
    if not deleted:
        return jsonify({"error": "project link not found"}), 404
    atlas_routes.log.info("ATLAS_PROJECT_LINK_REMOVED", extra={
        "ip": atlas_routes.get_client_ip(),
        "session": atlas_routes.get_log_session_id(session_id),
        "project_id": project_id,
        "entity_id": entity_id,
    })
    return jsonify({"ok": True})
