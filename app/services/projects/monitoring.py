# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project-scoped monitoring dashboard payloads."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import shlex
import time
from typing import Any
from urllib.parse import quote

from core.database_access import get_db_connect
from core.helpers import get_log_session_id
from services.diff.rollups import SEVERITY_NONE, SEVERITY_ORDER, build_fire_rollup
from services.projects.queries import _project_entity_owner_clause
from services.projects.scope import shared_owner_where
from services.scheduler.service import get_schedule
from services.watchers.models import (
    WATCHER_ACK_ACKNOWLEDGED,
    WATCHER_ACK_NEEDS_ACTION,
    WATCHER_ACK_NEW,
    WATCHER_FIRE_KIND_CHANGED,
    WATCHER_FIRE_KIND_FAILED,
    WATCHER_FIRE_KIND_RECOVERED,
    WATCHER_FIRE_KIND_UNCLASSIFIED,
    WATCHER_STATE_CHANGED,
    WATCHER_STATE_ERROR,
    WATCHER_STATE_FIRING,
    WATCHER_STATE_OK,
    WATCHER_STATE_PAUSED,
    Watcher,
    WatcherFire,
)
from services.watchers.serialization import watcher_fire_payload, watcher_payload
from services.watchers.service import get_watcher, list_watcher_fires, row_to_watcher, update_watcher_fire_ack
from services.watchers.service import row_to_watcher_fire

log = logging.getLogger("shell")

QUIET_NO_CHANGE_THRESHOLD = 3
UNRESOLVED_ACK_STATE_QUERY = (WATCHER_ACK_NEW, WATCHER_ACK_ACKNOWLEDGED, WATCHER_ACK_NEEDS_ACTION)
UNRESOLVED_ACK_STATES = frozenset(UNRESOLVED_ACK_STATE_QUERY)
GROUP_LABELS = {
    "ports": "External perimeter/ports",
    "hosts": "DNS/subdomains",
    "tls": "Certificates",
    "web": "Web checks",
    "findings": "Findings",
    "custom": "Custom commands",
}
SUMMARY_TOP_CHANGE_LIMIT = 5
WEB_COMMAND_ROOTS = frozenset({"curl", "httpx", "wget", "nikto", "whatweb"})
HOST_COMMAND_ROOTS = frozenset({"amass", "assetfinder", "dnsx", "subfinder"})
MISSING_REF_LOG_LIMIT = 10


def _value(row: Any, key: str, default: Any = "") -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return getattr(row, key, default)


def _project_row(conn, session_id: str, project_id: str, *, team_id: str = "") -> dict[str, Any] | None:
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="p")
    row = conn.execute(
        "SELECT p.id, p.session_id, p.team_id, p.name, p.slug, p.description, "
        "p.status, p.color, p.created, p.updated "
        "FROM projects p WHERE " + owner_sql + " AND p.id = ? LIMIT 1",  # nosec
        (*owner_params, project_id),
    ).fetchone()
    return dict(row) if row else None


def _run_refs(conn, session_id: str, run_ids: set[str], *, team_id: str = "") -> dict[str, dict[str, Any]]:
    ids = sorted(str(run_id or "").strip() for run_id in run_ids if str(run_id or "").strip())
    if not ids:
        return {}
    placeholders = ", ".join("?" for _ in ids)
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="r")
    rows = conn.execute(
        "SELECT r.id, r.command, r.started, r.finished, r.exit_code "
        "FROM runs r WHERE " + owner_sql + f" AND r.id IN ({placeholders})",  # nosec
        (*owner_params, *ids),
    ).fetchall()
    return {
        str(_value(row, "id")): {
            "id": str(_value(row, "id")),
            "command": str(_value(row, "command")),
            "started": str(_value(row, "started")),
            "finished": str(_value(row, "finished")),
            "exit_code": _value(row, "exit_code"),
        }
        for row in rows
    }


def _project_target_options(conn, session_id: str, project_id: str, *, team_id: str = "") -> list[dict[str, str]]:
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="p")
    entity_owner_sql, entity_owner_params = _project_entity_owner_clause(session_id, team_id=team_id, table_alias="e")
    rows = conn.execute(
        "SELECT e.id, e.type, e.canonical_value "
        "FROM project_links l "
        "JOIN projects p ON p.id = l.project_id "
        "JOIN entities e ON e.id = l.entity_id "
        "WHERE l.project_id = ? AND l.entity_type = 'atlas_entity' "
        "AND " + owner_sql + " " + entity_owner_sql  # nosec
        + "AND COALESCE(e.suppressed, FALSE) = FALSE "
        "AND e.type IN ('domain', 'ip', 'url') "
        "ORDER BY LOWER(e.canonical_value), e.id LIMIT 100",
        (project_id, *owner_params, *entity_owner_params),
    ).fetchall()
    return [
        {
            "id": str(_value(row, "id")),
            "type": str(_value(row, "type")),
            "value": str(_value(row, "canonical_value")),
        }
        for row in rows
        if str(_value(row, "canonical_value") or "").strip()
    ]


def _monitor_state(watcher) -> str:
    if watcher.state == WATCHER_STATE_CHANGED:
        return "changed"
    if watcher.state == WATCHER_STATE_ERROR:
        return "failed"
    if watcher.state == WATCHER_STATE_PAUSED:
        return "paused"
    if watcher.state == WATCHER_STATE_FIRING:
        return "active"
    if watcher.state == WATCHER_STATE_OK and watcher.consecutive_no_change >= QUIET_NO_CHANGE_THRESHOLD:
        return "quiet"
    return "active"


def _command_root(command: str) -> str:
    try:
        parts = shlex.split(str(command or ""))
    except ValueError:
        parts = str(command or "").split()
    while parts and parts[0] in {"sudo", "env", "time"}:
        parts = parts[1:]
    return str(parts[0] if parts else "").split("/")[-1].lower()


def _group_for(watcher, fires: list[dict[str, Any]]) -> dict[str, str]:
    classifier = str((fires[0].get("rollup") or {}).get("classifier") or "").lower() if fires else ""
    root = _command_root(watcher.command_text)
    if classifier == "ports" or root in {"masscan", "naabu", "nmap", "rustscan"}:
        key = "ports"
    elif classifier == "hosts" or root in HOST_COMMAND_ROOTS:
        key = "hosts"
    elif classifier == "tls" or root in {"openssl", "testssl.sh"}:
        key = "tls"
    elif classifier == "findings" or root in {"nuclei", "wpscan"}:
        key = "findings"
    elif root in WEB_COMMAND_ROOTS:
        key = "web"
    else:
        key = "custom"
    return {"key": key, "label": GROUP_LABELS[key], "command_root": root}


def _signal_text(fire: dict[str, Any]) -> str:
    rollup = _rollup_dict(fire)
    raw_signals = rollup.get("top_signals")
    signals = raw_signals if isinstance(raw_signals, list) else []
    return " ".join(str(signal.get("label") or "") for signal in signals if isinstance(signal, dict))


def _rollup_dict(fire: dict[str, Any]) -> dict[str, Any]:
    raw_rollup = fire.get("rollup")
    return raw_rollup if isinstance(raw_rollup, dict) else {}


def _latest_fire_dict(monitor: dict[str, Any]) -> dict[str, Any]:
    raw_fire = monitor.get("latest_fire")
    return raw_fire if isinstance(raw_fire, dict) else {}


def _matched_targets(text: str, target_options: list[dict[str, str]]) -> list[dict[str, str]]:
    haystack = str(text or "").lower()
    matches = []
    for target in target_options:
        value = str(target.get("value") or "").strip()
        if value and value.lower() in haystack:
            matches.append(target)
    return matches


def _counts(monitors: list[dict[str, Any]]) -> dict[str, int]:
    totals = {
        "active": 0,
        "changed": 0,
        "failed": 0,
        "quiet": 0,
        "paused": 0,
    }
    for monitor in monitors:
        state = str(monitor.get("dashboard_state") or "active")
        if state in totals:
            totals[state] += 1
    return totals


def _fire_payload(fire, watcher, run_refs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    payload = watcher_fire_payload(fire)
    payload["watcher_label"] = watcher.label or watcher.command_text
    payload["watcher_command"] = watcher.command_text
    payload["fire_kind"] = payload.get("fire_kind") or WATCHER_FIRE_KIND_UNCLASSIFIED
    run_id = str(payload.get("run_id") or "")
    baseline_id = str(payload.get("baseline_run_id") or "")
    payload["run"] = run_refs.get(run_id)
    payload["baseline_run"] = run_refs.get(baseline_id)
    payload["run_available"] = bool(run_id and payload["run"])
    payload["baseline_run_available"] = bool(baseline_id and payload["baseline_run"])
    payload["rollup"] = build_fire_rollup(
        fire.diff_summary,
        diff_kind=fire.diff_kind,
        truncated=fire.truncated,
        run_id=run_id,
        baseline_run_id=baseline_id,
    )
    return payload


def _latest_unresolved_fire(fires: list[dict[str, Any]]) -> dict[str, Any] | None:
    for fire in fires:
        if str(fire.get("ack_state") or "new") in UNRESOLVED_ACK_STATES:
            return fire
    return None


def _unresolved_summary_fires_for_project(
    conn,
    session_id: str,
    project_id: str,
    *,
    team_id: str = "",
) -> list[WatcherFire]:
    placeholders = ", ".join("?" for _ in UNRESOLVED_ACK_STATE_QUERY)
    owner_sql, owner_params = shared_owner_where(
        session_id,
        team_id=team_id,
        table_alias="w",
        session_column="session_token",
    )
    rows = conn.execute(
        "SELECT f.* FROM watcher_fires f "
        "JOIN watchers w ON w.id = f.watcher_id "
        "WHERE " + owner_sql + " AND w.project_id = ? "  # nosec
        "AND f.ack_state IN (" + placeholders + ") "  # nosec
        "ORDER BY f.created DESC, f.id DESC",
        (*owner_params, project_id, *UNRESOLVED_ACK_STATE_QUERY),
    ).fetchall()
    return [row_to_watcher_fire(row) for row in rows]


def _window_summary_fires_for_project(
    conn,
    session_id: str,
    project_id: str,
    *,
    team_id: str = "",
    window_start: str = "",
    window_end: str = "",
) -> list[WatcherFire]:
    owner_sql, owner_params = shared_owner_where(
        session_id,
        team_id=team_id,
        table_alias="w",
        session_column="session_token",
    )
    where = [" " + owner_sql, "w.project_id = ?"]
    params: list[Any] = [*owner_params, project_id]
    if window_start:
        where.append("f.created >= ?")
        params.append(window_start)
    if window_end:
        where.append("f.created < ?")
        params.append(window_end)
    rows = conn.execute(
        "SELECT f.* FROM watcher_fires f "
        "JOIN watchers w ON w.id = f.watcher_id "
        "WHERE " + " AND ".join(where) + " "  # nosec
        "ORDER BY f.created DESC, f.id DESC",
        params,
    ).fetchall()
    return [row_to_watcher_fire(row) for row in rows]


def _decorate_fire_targets(
    fire: dict[str, Any],
    watcher: Watcher,
    group: dict[str, str],
    target_options: list[dict[str, str]],
) -> None:
    fire["monitor_group"] = group
    fire["linked_targets"] = _matched_targets(
        f"{watcher.command_text} {_signal_text(fire)} {fire.get('watcher_label') or ''}",
        target_options,
    )


def _filter_option(items: set[str], labels: dict[str, str] | None = None) -> list[dict[str, str]]:
    rendered = []
    for item in sorted(str(value or "") for value in items if str(value or "").strip()):
        rendered.append({"value": item, "label": (labels or {}).get(item, item)})
    return rendered


def _filter_options(
    monitors: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
    targets: list[dict[str, str]],
) -> dict[str, Any]:
    severities = {
        str((fire.get("rollup") or {}).get("severity") or "")
        for fire in timeline
        if isinstance(fire.get("rollup"), dict)
        and str((fire.get("rollup") or {}).get("severity") or "") != SEVERITY_NONE
    }
    classifiers = {
        str((fire.get("rollup") or {}).get("classifier") or "")
        for fire in timeline
        if isinstance(fire.get("rollup"), dict)
    }
    return {
        "statuses": _filter_option({str(monitor.get("dashboard_state") or "") for monitor in monitors}),
        "severities": _filter_option(severities),
        "classifiers": _filter_option(classifiers),
        "cadences": _filter_option(
            {
                str((monitor.get("schedule") or {}).get("cadence_preset") or "")
                for monitor in monitors
            }
        ),
        "ack_states": _filter_option({str(fire.get("ack_state") or "new") for fire in timeline}),
        "groups": _filter_option(
            {
                str((monitor.get("monitor_group") or {}).get("key") or "")
                for monitor in monitors
            },
            GROUP_LABELS,
        ),
        "targets": targets,
    }


def _severity_rank(value: Any) -> int:
    return SEVERITY_ORDER.get(str(value or SEVERITY_NONE), 0)


def _monitoring_links(project_id: str) -> dict[str, str]:
    encoded = quote(str(project_id or "").strip(), safe="")
    return {
        "project_monitoring": f"/projects/{encoded}/monitoring",
        "project_monitoring_summary": f"/projects/{encoded}/monitoring/summary",
    }


def _monitoring_log_context(session_id: str, project_id: str, *, team_id: str = "", **extra: Any) -> dict[str, Any]:
    payload = {
        "session": get_log_session_id(session_id),
        "team_id": str(team_id or ""),
        "project_id": str(project_id or ""),
    }
    payload.update(extra)
    return payload


def _top_change_label(fire: dict[str, Any]) -> str:
    rollup = _rollup_dict(fire)
    raw_signals = rollup.get("top_signals")
    signals = raw_signals if isinstance(raw_signals, list) else []
    for signal in signals:
        if isinstance(signal, dict) and str(signal.get("label") or "").strip():
            return str(signal.get("label") or "").strip()
    kind = str(fire.get("fire_kind") or WATCHER_FIRE_KIND_UNCLASSIFIED).replace("_", " ")
    return f"{kind.title()} event"


def _fire_linked_targets(fire: dict[str, Any]) -> list[dict[str, str]]:
    raw_targets = fire.get("linked_targets")
    targets = raw_targets if isinstance(raw_targets, list) else []
    rendered = []
    seen_ids = set()
    for target in targets:
        if not isinstance(target, dict):
            continue
        target_id = str(target.get("id") or "").strip()
        if not target_id or target_id in seen_ids:
            continue
        seen_ids.add(target_id)
        rendered.append({
            "id": target_id,
            "type": str(target.get("type") or ""),
            "value": str(target.get("value") or ""),
        })
    return rendered


def _project_summary(
    project_id: str,
    counts: dict[str, int],
    monitors: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
) -> dict[str, Any]:
    if monitors:
        recovered_monitor_ids = {
            str(monitor.get("id") or "")
            for monitor in monitors
            if str(_latest_fire_dict(monitor).get("fire_kind") or "") == WATCHER_FIRE_KIND_RECOVERED
        }
    else:
        recovered_monitor_ids = {
            str(fire.get("watcher_id") or "")
            for fire in timeline
            if str(fire.get("fire_kind") or "") == WATCHER_FIRE_KIND_RECOVERED
        }
    highest_severity = SEVERITY_NONE
    for fire in timeline:
        rollup = _rollup_dict(fire)
        severity = str(rollup.get("severity") or SEVERITY_NONE)
        if _severity_rank(severity) > _severity_rank(highest_severity):
            highest_severity = severity

    ranked_changes = sorted(
        timeline,
        key=lambda item: (
            _severity_rank(_rollup_dict(item).get("severity")),
            str(item.get("created") or ""),
            str(item.get("id") or ""),
        ),
        reverse=True,
    )
    top_changes = []
    for fire in ranked_changes:
        rollup = _rollup_dict(fire)
        severity = str(rollup.get("severity") or SEVERITY_NONE)
        fire_kind = str(fire.get("fire_kind") or WATCHER_FIRE_KIND_UNCLASSIFIED)
        if severity == SEVERITY_NONE and fire_kind not in {"failed", "recovered"}:
            continue
        linked_targets = _fire_linked_targets(fire)
        top_changes.append({
            "fire_id": str(fire.get("id") or ""),
            "watcher_id": str(fire.get("watcher_id") or ""),
            "watcher_label": str(fire.get("watcher_label") or ""),
            "fire_kind": fire_kind,
            "created": str(fire.get("created") or ""),
            "severity": severity,
            "classifier": str(rollup.get("classifier") or ""),
            "label": _top_change_label(fire),
            "run_id": str(fire.get("run_id") or ""),
            "baseline_run_id": str(fire.get("baseline_run_id") or ""),
            "run_available": bool(fire.get("run_available")),
            "baseline_run_available": bool(fire.get("baseline_run_available")),
            "target_ids": [target["id"] for target in linked_targets],
            "linked_targets": linked_targets,
        })
        if len(top_changes) >= SUMMARY_TOP_CHANGE_LIMIT:
            break

    return {
        "changed_monitor_count": int(counts.get("changed") or 0),
        "recovered_monitor_count": len({item for item in recovered_monitor_ids if item}),
        "failed_monitor_count": int(counts.get("failed") or 0),
        "highest_severity": highest_severity,
        "top_changes": top_changes,
        "links": _monitoring_links(project_id),
}


def _window_summary_counts(timeline: list[dict[str, Any]]) -> dict[str, int]:
    changed = set()
    failed = set()
    for fire in timeline:
        watcher_id = str(fire.get("watcher_id") or "")
        fire_kind = str(fire.get("fire_kind") or WATCHER_FIRE_KIND_UNCLASSIFIED)
        if fire_kind == WATCHER_FIRE_KIND_CHANGED and watcher_id:
            changed.add(watcher_id)
        elif fire_kind == WATCHER_FIRE_KIND_FAILED and watcher_id:
            failed.add(watcher_id)
    return {
        "changed": len(changed),
        "failed": len(failed),
    }


def get_project_monitoring(
    session_id: str,
    project_id: str,
    *,
    team_id: str = "",
    fire_limit: int = 8,
    summary_window_start: str = "",
    summary_window_end: str = "",
) -> dict[str, Any] | None:
    normalized_project_id = str(project_id or "").strip()
    if not normalized_project_id:
        log.debug(
            "PROJECT_MONITORING_PROJECT_MISS",
            extra=_monitoring_log_context(session_id, project_id, team_id=team_id, reason="blank_project_id"),
        )
        return None
    started = time.perf_counter()
    safe_fire_limit = max(1, min(int(fire_limit or 8), 25))
    with get_db_connect()() as conn:
        project = _project_row(conn, session_id, normalized_project_id, team_id=team_id)
        if project is None:
            log.debug(
                "PROJECT_MONITORING_PROJECT_MISS",
                extra=_monitoring_log_context(session_id, normalized_project_id, team_id=team_id, reason="not_found"),
            )
            return None
        owner_sql, owner_params = shared_owner_where(
            session_id,
            team_id=team_id,
            table_alias="w",
            session_column="session_token",
        )
        rows = conn.execute(
            "SELECT w.* FROM watchers w "
            "WHERE " + owner_sql + " AND w.project_id = ? "  # nosec
            "ORDER BY w.updated DESC, w.id DESC",
            (*owner_params, normalized_project_id),
        ).fetchall()
        watchers = [row_to_watcher(row) for row in rows]
        watchers_by_id = {watcher.id: watcher for watcher in watchers}
        summary_fire_rows = _unresolved_summary_fires_for_project(
            conn,
            session_id,
            normalized_project_id,
            team_id=team_id,
        )
        window_fire_rows = []
        if summary_window_start or summary_window_end:
            window_fire_rows = _window_summary_fires_for_project(
                conn,
                session_id,
                normalized_project_id,
                team_id=team_id,
                window_start=str(summary_window_start or ""),
                window_end=str(summary_window_end or ""),
            )
        unresolved_fires_by_watcher = {}
        for fire in summary_fire_rows:
            unresolved_fires_by_watcher.setdefault(fire.watcher_id, fire)
        fires_by_watcher = {}
        run_ids: set[str] = set()
        requested_run_ids: set[str] = set()
        requested_baseline_ids: set[str] = set()
        for watcher in watchers:
            fires, _total = list_watcher_fires(watcher.id, limit=safe_fire_limit, conn=conn)
            fires_by_watcher[watcher.id] = fires
            if watcher.baseline_run_id:
                run_ids.add(watcher.baseline_run_id)
                requested_baseline_ids.add(watcher.baseline_run_id)
            if watcher.last_run_id:
                run_ids.add(watcher.last_run_id)
                requested_run_ids.add(watcher.last_run_id)
            for fire in fires:
                if fire.run_id:
                    run_ids.add(fire.run_id)
                    requested_run_ids.add(fire.run_id)
                if fire.baseline_run_id:
                    run_ids.add(fire.baseline_run_id)
                    requested_baseline_ids.add(fire.baseline_run_id)
        for fire in summary_fire_rows:
            if fire.run_id:
                run_ids.add(fire.run_id)
                requested_run_ids.add(fire.run_id)
            if fire.baseline_run_id:
                run_ids.add(fire.baseline_run_id)
                requested_baseline_ids.add(fire.baseline_run_id)
        for fire in window_fire_rows:
            if fire.run_id:
                run_ids.add(fire.run_id)
                requested_run_ids.add(fire.run_id)
            if fire.baseline_run_id:
                run_ids.add(fire.baseline_run_id)
                requested_baseline_ids.add(fire.baseline_run_id)
        run_refs = _run_refs(conn, session_id, run_ids, team_id=team_id)
        monitors = []
        timeline = []
        groups_by_watcher: dict[str, dict[str, str]] = {}
        target_options = _project_target_options(conn, session_id, normalized_project_id, team_id=team_id)
        for watcher in watchers:
            schedule = get_schedule(watcher.schedule_id, conn=conn)
            fires = [
                _fire_payload(fire, watcher, run_refs)
                for fire in fires_by_watcher.get(watcher.id, [])
            ]
            group = _group_for(watcher, fires)
            groups_by_watcher[watcher.id] = group
            for fire in fires:
                _decorate_fire_targets(fire, watcher, group, target_options)
            timeline.extend(fires)
            payload = watcher_payload(watcher, schedule=schedule)
            payload["baseline_run"] = run_refs.get(watcher.baseline_run_id)
            payload["last_run"] = run_refs.get(watcher.last_run_id)
            payload["dashboard_state"] = _monitor_state(watcher)
            payload["monitor_group"] = group
            raw_unresolved_fire = unresolved_fires_by_watcher.get(watcher.id)
            unresolved_fire = (
                _fire_payload(raw_unresolved_fire, watcher, run_refs)
                if raw_unresolved_fire is not None
                else _latest_unresolved_fire(fires)
            )
            if unresolved_fire is not None:
                _decorate_fire_targets(unresolved_fire, watcher, group, target_options)
            payload["current_triage_state"] = str(unresolved_fire.get("ack_state") or "new") if unresolved_fire else "resolved"
            payload["current_triage_fire"] = unresolved_fire
            payload["linked_targets"] = _matched_targets(
                " ".join([
                    watcher.label,
                    watcher.command_text,
                    " ".join(_signal_text(fire) for fire in fires),
                ]),
                target_options,
            )
            monitors.append({
                **payload,
                "fires": fires,
                "latest_fire": fires[0] if fires else None,
            })
        summary_timeline = []
        for raw_fire in summary_fire_rows:
            watcher = watchers_by_id.get(raw_fire.watcher_id)
            if watcher is None:
                continue
            fire = _fire_payload(raw_fire, watcher, run_refs)
            group = groups_by_watcher.get(watcher.id) or _group_for(watcher, [])
            _decorate_fire_targets(fire, watcher, group, target_options)
            summary_timeline.append(fire)
        window_timeline = []
        for raw_fire in window_fire_rows:
            watcher = watchers_by_id.get(raw_fire.watcher_id)
            if watcher is None:
                continue
            fire = _fire_payload(raw_fire, watcher, run_refs)
            group = groups_by_watcher.get(watcher.id) or _group_for(watcher, [])
            _decorate_fire_targets(fire, watcher, group, target_options)
            window_timeline.append(fire)
        timeline.sort(key=lambda item: (str(item.get("created") or ""), str(item.get("id") or "")), reverse=True)
        window_timeline.sort(key=lambda item: (str(item.get("created") or ""), str(item.get("id") or "")), reverse=True)
        counts = _counts(monitors)
        visible_timeline = timeline[: max(25, safe_fire_limit)]
        summary = _project_summary(normalized_project_id, counts, monitors, summary_timeline)
        window_summary = None
        if summary_window_start or summary_window_end:
            window_summary = _project_summary(
                normalized_project_id,
                _window_summary_counts(window_timeline),
                [],
                window_timeline,
            )
        missing_run_ids = sorted(run_id for run_id in requested_run_ids if run_id not in run_refs)
        missing_baseline_run_ids = sorted(run_id for run_id in requested_baseline_ids if run_id not in run_refs)
        if missing_run_ids or missing_baseline_run_ids:
            affected_monitor_ids = sorted({
                str(monitor.get("id") or "")
                for monitor in monitors
                if (
                    str(monitor.get("last_run_id") or "") in missing_run_ids
                    or str(monitor.get("baseline_run_id") or "") in missing_baseline_run_ids
                    or any(
                        str(fire.get("run_id") or "") in missing_run_ids
                        or str(fire.get("baseline_run_id") or "") in missing_baseline_run_ids
                        for fire in monitor.get("fires", [])
                    )
                )
            })
            missing_fire_ids = sorted({
                str(fire.get("id") or "")
                for fire in timeline
                if (
                    str(fire.get("run_id") or "") in missing_run_ids
                    or str(fire.get("baseline_run_id") or "") in missing_baseline_run_ids
                )
            })
            log.warning(
                "PROJECT_MONITORING_RUN_REF_MISSING",
                extra=_monitoring_log_context(
                    session_id,
                    normalized_project_id,
                    team_id=team_id,
                    missing_run_count=len(missing_run_ids),
                    missing_baseline_count=len(missing_baseline_run_ids),
                    affected_monitor_count=len([item for item in affected_monitor_ids if item]),
                    watcher_ids=",".join(affected_monitor_ids[:MISSING_REF_LOG_LIMIT]),
                    fire_ids=",".join(missing_fire_ids[:MISSING_REF_LOG_LIMIT]),
                ),
            )
            log.debug(
                "PROJECT_MONITORING_RUN_REF_MISSING_DETAIL",
                extra=_monitoring_log_context(
                    session_id,
                    normalized_project_id,
                    team_id=team_id,
                    missing_run_ids=",".join(missing_run_ids[:MISSING_REF_LOG_LIMIT]),
                    missing_baseline_run_ids=",".join(missing_baseline_run_ids[:MISSING_REF_LOG_LIMIT]),
                ),
            )
        duration_ms = int((time.perf_counter() - started) * 1000)
        windowed = window_summary is not None
        window_counts = _window_summary_counts(window_timeline) if windowed else {}
        log.debug(
            "PROJECT_MONITORING_PAYLOAD_BUILT",
            extra=_monitoring_log_context(
                session_id,
                normalized_project_id,
                team_id=team_id,
                fire_limit=safe_fire_limit,
                watcher_count=len(watchers),
                timeline_count=len(visible_timeline),
                target_count=len(target_options),
                run_ref_requested_count=len(run_ids),
                run_ref_found_count=len(run_refs),
                counts=counts,
                windowed=windowed,
                window_start=str(summary_window_start or ""),
                window_end=str(summary_window_end or ""),
                window_fire_count=len(window_timeline),
                window_counts=window_counts,
                duration_ms=duration_ms,
            ),
        )
        payload = {
            "project": project,
            "counts": counts,
            "summary": summary,
            "quiet_no_change_threshold": QUIET_NO_CHANGE_THRESHOLD,
            "monitors": monitors,
            "timeline": visible_timeline,
            "filter_options": _filter_options(monitors, timeline, target_options),
        }
        if window_summary is not None:
            payload["digest_window"] = {
                "start": str(summary_window_start or ""),
                "end": str(summary_window_end or ""),
                "fire_count": len(window_timeline),
            }
            payload["window_summary"] = window_summary
        return payload


def get_project_monitoring_summary(
    session_id: str,
    project_id: str,
    *,
    team_id: str = "",
    fire_limit: int = 8,
    window_start: str = "",
    window_end: str = "",
) -> dict[str, Any] | None:
    payload = get_project_monitoring(
        session_id,
        project_id,
        team_id=team_id,
        fire_limit=fire_limit,
        summary_window_start=window_start,
        summary_window_end=window_end,
    )
    if payload is None:
        return None
    summary_payload = {
        "project": payload["project"],
        "counts": payload["counts"],
        "summary": payload["summary"],
    }
    if "window_summary" in payload:
        summary_payload["digest_window"] = payload["digest_window"]
        summary_payload["window_summary"] = payload["window_summary"]
    return summary_payload


def update_project_monitoring_fire_ack(
    session_id: str,
    project_id: str,
    fire_id: str,
    *,
    ack_state: str,
    ack_note: str = "",
    ack_by: str = "",
    team_id: str = "",
) -> tuple[Watcher, WatcherFire] | None:
    normalized_project_id = str(project_id or "").strip()
    normalized_fire_id = str(fire_id or "").strip()
    if not normalized_project_id or not normalized_fire_id:
        log.debug(
            "PROJECT_MONITORING_FIRE_ACK_LOOKUP_MISS",
            extra=_monitoring_log_context(
                session_id,
                normalized_project_id,
                team_id=team_id,
                fire_id=normalized_fire_id,
                reason="blank_input",
            ),
        )
        return None
    with get_db_connect()() as conn:
        owner_sql, owner_params = shared_owner_where(
            session_id,
            team_id=team_id,
            table_alias="w",
            session_column="session_token",
        )
        row = conn.execute(
            "SELECT w.id, f.ack_state FROM watcher_fires f "
            "JOIN watchers w ON w.id = f.watcher_id "
            "WHERE " + owner_sql + " AND w.project_id = ? AND f.id = ? LIMIT 1",  # nosec
            (*owner_params, normalized_project_id, normalized_fire_id),
        ).fetchone()
        if row is None:
            log.debug(
                "PROJECT_MONITORING_FIRE_ACK_LOOKUP_MISS",
                extra=_monitoring_log_context(
                    session_id,
                    normalized_project_id,
                    team_id=team_id,
                    fire_id=normalized_fire_id,
                    reason="scope_miss",
                ),
            )
            return None
        watcher = get_watcher(str(_value(row, "id")), conn=conn)
        if watcher is None:
            log.debug(
                "PROJECT_MONITORING_FIRE_ACK_LOOKUP_MISS",
                extra=_monitoring_log_context(
                    session_id,
                    normalized_project_id,
                    team_id=team_id,
                    fire_id=normalized_fire_id,
                    reason="watcher_missing",
                ),
            )
            return None
        previous_ack_state = str(_value(row, "ack_state") or WATCHER_ACK_NEW)
        updated = update_watcher_fire_ack(
            conn,
            normalized_fire_id,
            ack_state=ack_state,
            ack_note=str(ack_note or "").strip()[:1000],
            ack_by=str(ack_by or "").strip(),
            ack_at=datetime.now(timezone.utc).isoformat(),
        )
        if updated is None:
            log.debug(
                "PROJECT_MONITORING_FIRE_ACK_LOOKUP_MISS",
                extra=_monitoring_log_context(
                    session_id,
                    normalized_project_id,
                    team_id=team_id,
                    fire_id=normalized_fire_id,
                    reason="fire_missing",
                ),
            )
            return None
        log.debug(
            "PROJECT_MONITORING_FIRE_ACK_STATE_CHANGED",
            extra=_monitoring_log_context(
                session_id,
                normalized_project_id,
                team_id=team_id,
                watcher_id=watcher.id,
                fire_id=updated.id,
                from_ack_state=previous_ack_state,
                to_ack_state=updated.ack_state,
                note_chars=len(updated.ack_note),
            ),
        )
        conn.commit()
        return watcher, updated
