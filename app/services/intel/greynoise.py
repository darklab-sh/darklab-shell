# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""GreyNoise provider normalization."""

from __future__ import annotations

from typing import Any

from services.intel.base import IntelResult, Provider, ProviderApiError, ProviderClientUnavailable
from services.intel.canonical import canonical_ip
from services.intel.registry import provider_definition
from services.intel.schema import response_with_provider


def normalize_ip_payload(raw: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "classification": str(raw.get("classification") or ""),
        "name": str(raw.get("name") or ""),
        "last_seen": str(raw.get("last_seen") or ""),
    }
    message = str(raw.get("message") or "").strip()
    if message:
        payload["message"] = message
    for key in ("noise", "riot"):
        if isinstance(raw.get(key), bool):
            payload[key] = raw[key]
    link = str(raw.get("link") or "").strip()
    if link:
        payload["link"] = link
    return payload


def _is_not_observed_response(exc: ProviderApiError) -> bool:
    message = str(exc).strip().lower()
    return (
        exc.status == 404
        and "not observed scanning the internet" in message
        and "riot" in message
    )


class GreyNoiseProvider(Provider):
    def __init__(self, **kwargs):
        definition = provider_definition("greynoise")
        super().__init__(
            name="greynoise",
            secret_env=definition.secret_env if definition else "GREYNOISE_API_KEY",
            cache_scopes=definition.cache_scopes if definition else {"ip": "ip"},
            **kwargs,
        )

    def lookup_ip(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        api_key = self.secret_value(session_token)
        if not self.client:
            raise ProviderClientUnavailable("GreyNoise client is not configured")
        canonical = canonical_ip(value)
        try:
            raw = self.client.lookup_ip(canonical, api_key=api_key)
        except ProviderApiError as exc:
            if not _is_not_observed_response(exc):
                raise
            raw = {"message": str(exc)}
        payload = response_with_provider("ip", self.name, normalize_ip_payload(raw))
        return IntelResult(self.name, "ip", canonical, payload, http_status=getattr(self.client, "last_status", None))
