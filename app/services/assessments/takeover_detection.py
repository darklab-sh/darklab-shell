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
    in_scope = item.get("in_scope") is not False and scope_decision != "out_of_scope"
    template_match = bool(item.get("reviewed_takeover_template_match"))
    target_resolution = _text(item.get("target_resolution_state")).casefold()
    if target_resolution in {"transient", "uncertain"}:
        return {"state": "uncertain", "reason": "transient_dns_result", "hostname": hostname}
    dangling = bool(
        cname_chain
        and (item.get("target_resolved") is False or target_resolution == "negative")
    )
    if not dangling:
        return {"state": "not_indicated", "hostname": hostname}
    result = {
        "state": "confirmed" if template_match and in_scope else "potential",
        "reason": "reviewed_provider_match" if template_match and in_scope else "dangling_cname",
        "hostname": hostname,
        "cname_chain": cname_chain[:16],
        "provider": provider,
    }
    if _text(item.get("wildcard_filter")).casefold() == "not_checked":
        result["uncertainties"] = ["wildcard_not_checked"]
    if not in_scope:
        result["state"] = "uncertain"
        result["reason"] = "out_of_scope_target"
    return result


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())[:512]


__all__ = ["evaluate_takeover_signal"]
