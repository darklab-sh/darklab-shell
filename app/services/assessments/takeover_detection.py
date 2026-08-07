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
    provider = _text(item.get("provider")).casefold()
    in_scope = item.get("in_scope") is not False
    template_match = bool(item.get("reviewed_takeover_template_match"))
    dangling = bool(cname_chain and item.get("target_resolved") is False)
    if not dangling:
        return {"state": "not_indicated", "hostname": hostname}
    result = {
        "state": "confirmed" if template_match and in_scope else "potential",
        "reason": "reviewed_provider_match" if template_match and in_scope else "dangling_cname",
        "hostname": hostname,
        "cname_chain": cname_chain[:16],
        "provider": provider,
    }
    if not in_scope:
        result["state"] = "uncertain"
        result["reason"] = "out_of_scope_target"
    return result


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())[:512]


__all__ = ["evaluate_takeover_signal"]
