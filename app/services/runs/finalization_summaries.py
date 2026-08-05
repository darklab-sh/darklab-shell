# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded summary helpers for completed-run reporting."""

from __future__ import annotations


AUTO_PROMOTE_RUN_LOG_RESULT_LIMIT = 10


def auto_promote_summary_results(summary) -> list[dict]:
    if not isinstance(summary, dict):
        return []
    results = summary.get("results")
    if not isinstance(results, list):
        return []
    return [result for result in results if isinstance(result, dict)]


def auto_promote_summary_ids(results: list[dict], key: str) -> list[str]:
    return sorted({
        str(result.get(key) or "")
        for result in results
        if str(result.get(key) or "")
    })


def auto_promote_summary_log_results(results: list[dict]) -> list[dict[str, object]]:
    safe_results = []
    for result in results[:AUTO_PROMOTE_RUN_LOG_RESULT_LIMIT]:
        safe_results.append({
            "project_id": str(result.get("project_id") or ""),
            "rule_id": str(result.get("rule_id") or ""),
            "matched_count": int(result.get("matched_count") or 0),
            "linked_count": int(result.get("linked_count") or 0),
            "promoted_count": int(result.get("promoted_count") or 0),
            "quota_limited_count": int(result.get("quota_limited_count") or 0),
            "match_cap_limited_count": int(result.get("match_cap_limited_count") or 0),
        })
    return safe_results
