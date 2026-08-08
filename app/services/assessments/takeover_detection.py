# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Non-destructive dangling-record and takeover signal evaluation."""

from __future__ import annotations

from typing import Any


def evaluate_takeover_signal(observation: dict[str, Any] | None) -> dict[str, Any]:
    """Classify normalized DNS evidence without making network or claim actions."""
    item = observation if isinstance(observation, dict) else {}
    hostname = _text(item.get("hostname"))
    if not hostname:
        return {"state": "uncertain", "reason": "missing_hostname"}
    resolution = _text(item.get("resolution_state")).casefold()
    if resolution in {"timeout", "servfail", "unknown", "error"}:
        return {"state": "uncertain", "reason": "transient_dns_result", "hostname": hostname}
    cname_chain = [
        _text(value).casefold().rstrip(".")
        for value in item.get("cname_chain", [])
        if _text(value)
    ] if isinstance(item.get("cname_chain"), list) else []
    provider_row = item.get("provider_fingerprint")
    provider = _text(
        provider_row.get("name") if isinstance(provider_row, dict) else item.get("provider")
    ).casefold()
    scope_decision = _text(item.get("scope_decision")).casefold()
    in_scope = (
        scope_decision == "in_scope"
        if scope_decision
        else item.get("in_scope") is not False
    )
    target_resolution = _text(item.get("target_resolution_state")).casefold()
    if target_resolution in {"transient", "uncertain", "unknown"}:
        return {"state": "uncertain", "reason": "transient_dns_result", "hostname": hostname}
    dangling = bool(
        cname_chain
        and (item.get("target_resolved") is False or target_resolution == "negative")
    )
    if not dangling:
        return {"state": "not_indicated", "hostname": hostname}
    result = {
        "state": "potential",
        "reason": "dangling_cname",
        "hostname": hostname,
        "cname_chain": cname_chain[:16],
        "provider": provider,
    }
    target_observation = _target_reference(item.get("target_observation"))
    if target_observation:
        result["target_observation"] = target_observation
    if _text(item.get("wildcard_filter")).casefold() == "not_checked":
        result["uncertainties"] = ["wildcard_not_checked"]
    if not in_scope:
        result["state"] = "uncertain"
        result["reason"] = "unscoped_target" if scope_decision == "unknown" else "out_of_scope_target"
    return result


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())[:512]


def _target_reference(value: Any) -> dict[str, str]:
    item = value if isinstance(value, dict) else {}
    row = {
        key: _text(item.get(key))
        for key in (
            "observation_id", "source_run_id", "hostname", "resolution_state",
            "status_code", "scope_decision", "observed_at", "parser_version",
        )
        if _text(item.get(key))
    }
    return row if row.get("observation_id") and row.get("source_run_id") else {}


__all__ = ["evaluate_takeover_signal"]
