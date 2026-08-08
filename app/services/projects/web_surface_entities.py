# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Exact Atlas entity links for Project Web Surface captures."""

from __future__ import annotations

from urllib.parse import urlsplit

from services.intel.canonical import (
    CanonicalizationError,
    canonical_domain,
    canonical_ip,
    canonical_url,
)
from services.projects.scope import shared_owner_where


def attach_capture_entity_ids(conn, session_id: str, captures: list[dict[str, object]], *, team_id="") -> None:
    run_ids = sorted({str(item["source_run"]["id"]) for item in captures if item.get("url")})
    url_values = sorted({_canonical_capture_url(item.get("url")) for item in captures} - {""})
    host_values = sorted({_capture_host(item.get("url")) for item in captures} - {""})
    if not run_ids or not url_values:
        return
    run_placeholders = ",".join("?" for _ in run_ids)
    value_placeholders = ",".join("?" for _ in (*url_values, *host_values))
    entity_owner_sql, entity_owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="e",
    )
    entity_filter_sql = (
        f"erl.run_id IN ({run_placeholders}) AND "
        + entity_owner_sql
        + " AND e.type IN ('url', 'domain', 'ip') "
        + f"AND e.canonical_value IN ({value_placeholders})"
    )
    rows = conn.execute(
        "SELECT erl.run_id, e.id, e.type, e.canonical_value, e.host_entity_id "  # nosec B608
        "FROM entity_run_links erl JOIN entities e ON e.id = erl.entity_id WHERE "
        + entity_filter_sql,
        (*run_ids, *entity_owner_params, *url_values, *host_values),
    ).fetchall()
    linked = {(str(row["run_id"]), str(row["type"]), str(row["canonical_value"])): row for row in rows}
    linked_ids = {(str(row["run_id"]), str(row["id"])) for row in rows}
    for capture in captures:
        run_id = str(capture["source_run"]["id"])
        url_row = linked.get((run_id, "url", _canonical_capture_url(capture.get("url"))))
        host_value = _capture_host(capture.get("url"))
        host_type = _host_type(host_value)
        host_row = linked.get((run_id, host_type, host_value)) if host_type else None
        if url_row:
            capture["url_entity_id"] = str(url_row["id"] or "")
            url_host_id = str(url_row["host_entity_id"] or "")
            if url_host_id and (run_id, url_host_id) in linked_ids:
                capture["host_entity_id"] = url_host_id
        if not capture["host_entity_id"] and host_row:
            capture["host_entity_id"] = str(host_row["id"] or "")


def _canonical_capture_url(value: object) -> str:
    try:
        return canonical_url(str(value or ""))
    except CanonicalizationError:
        return ""


def _capture_host(value: object) -> str:
    host = str(urlsplit(str(value or "")).hostname or "")
    try:
        return canonical_ip(host)
    except CanonicalizationError:
        try:
            return canonical_domain(host)
        except CanonicalizationError:
            return ""


def _host_type(value: str) -> str:
    if not value:
        return ""
    try:
        canonical_ip(value)
    except CanonicalizationError:
        return "domain"
    return "ip"


__all__ = ["attach_capture_entity_ids"]
