# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared provider evidence for Atlas entity profiles and Project Overview."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from services.atlas.intel_profile import _snapshot_has_intel


CERT_STATUS_EXPIRED = "expired"
CERT_STATUS_EXPIRING_14D = "expiring_14d"
CERT_STATUS_EXPIRING_30D = "expiring_30d"
CERT_STATUS_HEALTHY = "healthy"
CERT_STATUS_UNKNOWN = "unknown"
CERT_STATUS_ORDER = (
    CERT_STATUS_EXPIRED,
    CERT_STATUS_EXPIRING_14D,
    CERT_STATUS_EXPIRING_30D,
    CERT_STATUS_HEALTHY,
    CERT_STATUS_UNKNOWN,
)

PROVIDER_PORT_LIST_LIMIT = 24
PROVIDER_SERVICE_LIST_LIMIT = 24

log = logging.getLogger("shell")


def classify_certificate_status(days_until_expiry: int | None, *, has_certificate_data: bool = True) -> str:
    if not has_certificate_data or days_until_expiry is None:
        return CERT_STATUS_UNKNOWN
    if days_until_expiry < 0:
        return CERT_STATUS_EXPIRED
    if days_until_expiry <= 14:
        return CERT_STATUS_EXPIRING_14D
    if days_until_expiry <= 30:
        return CERT_STATUS_EXPIRING_30D
    return CERT_STATUS_HEALTHY


def empty_certificate_evidence() -> dict[str, Any]:
    return {
        "status": CERT_STATUS_UNKNOWN,
        "expires_at": "",
        "days_until_expiry": None,
        "last_checked_at": "",
    }


def extract_intel_evidence(
    snapshots: Sequence[Mapping[str, Any]],
    *,
    entity_id: str = "",
    log_context: Mapping[str, Any] | None = None,
    log_event_namespace: str = "ATLAS_ENTITY_PROFILE",
) -> dict[str, Any]:
    """Extract bounded provider ports, services, and certificate evidence."""
    open_ports: list[int] = []
    services: list[str] = []
    cert_expires_at = ""
    cert_days: int | None = None
    has_cert_data = False
    latest_fetched = ""
    invalid_cert_dates: dict[str, int] = defaultdict(int)
    event_namespace = str(log_event_namespace or "ATLAS_ENTITY_PROFILE").strip().upper()
    for snapshot in _extraction_snapshots(snapshots):
        latest_fetched = max(latest_fetched, str(snapshot.get("fetched_at") or ""))
        for provider, payload in _provider_payloads(
            snapshot,
            entity_id=entity_id,
            log_context=log_context,
            log_event_namespace=event_namespace,
        ):
            for port in _payload_ports(payload):
                if port not in open_ports:
                    open_ports.append(port)
            for service in _payload_services(payload):
                if service not in services:
                    services.append(service)
            expiry = _certificate_expiry_from_payload(payload)
            if not expiry:
                continue
            has_cert_data = True
            days_until = _days_until(expiry)
            if days_until is None:
                invalid_cert_dates[provider] += 1
                continue
            if not cert_expires_at or expiry < cert_expires_at:
                cert_expires_at = expiry
                cert_days = days_until
    for provider, invalid_count in invalid_cert_dates.items():
        log.warning(f"{event_namespace}_CERT_DATE_PARSE_FAILED", extra={
            **dict(log_context or {}),
            "entity_id": entity_id,
            "provider": provider,
            "invalid_cert_date_count": invalid_count,
        })
    open_ports.sort()
    services.sort(key=str.lower)
    return {
        "open_ports": open_ports[:PROVIDER_PORT_LIST_LIMIT],
        "services": services[:PROVIDER_SERVICE_LIST_LIMIT],
        "certificate": {
            "status": classify_certificate_status(cert_days, has_certificate_data=has_cert_data),
            "expires_at": cert_expires_at,
            "days_until_expiry": cert_days,
            "last_checked_at": latest_fetched,
        },
    }


def port_provenance(
    app_ports: Sequence[Mapping[str, Any]],
    provider_ports: Sequence[int],
    app_evidence: Mapping[str, Any],
    *,
    has_provider_intel: bool,
) -> dict[str, Any]:
    """Compare app-observed and provider-reported port numbers."""
    public_app_ports = [dict(port) for port in app_ports]
    public_provider_ports = [int(port) for port in provider_ports if isinstance(port, int)]
    app_numbers = {
        int(port["port"])
        for port in public_app_ports
        if isinstance(port.get("port"), int)
    }
    provider_numbers = set(public_provider_ports)
    app_only = sorted(app_numbers - provider_numbers)
    provider_only = sorted(provider_numbers - app_numbers)
    has_app_scan = int(app_evidence.get("scan_run_count") or 0) > 0
    has_drift = has_app_scan and (bool(provider_only) or (has_provider_intel and bool(app_only)))
    return {
        "app": public_app_ports,
        "provider": public_provider_ports,
        "divergence": {
            "app_only": app_only,
            "provider_only": provider_only,
            "has_drift": has_drift,
        },
    }


def _latest_snapshots_by_provider(
    snapshots: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    latest_by_provider: dict[str, Mapping[str, Any]] = {}
    for snapshot in snapshots:
        provider = str(snapshot.get("provider") or "").strip().lower()
        if not provider:
            provider = str(snapshot.get("id") or "")
        current = latest_by_provider.get(provider)
        if current is None or str(snapshot.get("fetched_at") or "") > str(current.get("fetched_at") or ""):
            latest_by_provider[provider] = snapshot
    return sorted(
        latest_by_provider.values(),
        key=lambda snapshot: (str(snapshot.get("fetched_at") or ""), str(snapshot.get("provider") or "")),
        reverse=True,
    )


def _extraction_snapshots(snapshots: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    latest_snapshots = _latest_snapshots_by_provider(snapshots)
    fresh_snapshots = [
        snapshot for snapshot in latest_snapshots
        if _snapshot_has_intel(snapshot) and not _is_past_datetime(snapshot.get("expires_at"))
    ]
    return fresh_snapshots or latest_snapshots


def _provider_payloads(
    snapshot: Mapping[str, Any],
    *,
    entity_id: str,
    log_context: Mapping[str, Any] | None,
    log_event_namespace: str,
) -> list[tuple[str, dict[str, Any]]]:
    data = snapshot.get("data") if isinstance(snapshot.get("data"), Mapping) else {}
    providers = data.get("providers") if isinstance(data, Mapping) else {}
    if not isinstance(providers, dict):
        _log_skipped_provider_payload(
            snapshot,
            entity_id,
            provider="",
            payload=providers,
            log_context=log_context,
            log_event_namespace=log_event_namespace,
        )
        return []
    payloads = []
    for provider, payload in providers.items():
        provider_id = str(provider or "")
        if isinstance(payload, dict):
            payloads.append((provider_id, payload))
        else:
            _log_skipped_provider_payload(
                snapshot,
                entity_id,
                provider=provider_id,
                payload=payload,
                log_context=log_context,
                log_event_namespace=log_event_namespace,
            )
    return payloads


def _log_skipped_provider_payload(
    snapshot: Mapping[str, Any],
    entity_id: str,
    *,
    provider: str,
    payload: object,
    log_context: Mapping[str, Any] | None,
    log_event_namespace: str,
) -> None:
    status = str(snapshot.get("status") or "")
    event_extra = {
        **dict(log_context or {}),
        "entity_id": entity_id,
        "snapshot_id": str(snapshot.get("id") or ""),
        "provider": provider,
        "provider_status": status,
        "shape": type(payload).__name__,
    }
    event_name = f"{log_event_namespace}_INTEL_PAYLOAD_SKIPPED"
    if status == "ok":
        log.warning(event_name, extra=event_extra)
    else:
        log.debug(event_name, extra=event_extra)


def _payload_ports(payload: Mapping[str, Any]) -> list[int]:
    values: list[int] = []
    raw_ports = payload.get("ports")
    if isinstance(raw_ports, list):
        for item in raw_ports:
            port = _int_value(item)
            if port is not None and 0 < port <= 65535:
                values.append(port)
    raw_results = payload.get("results")
    if isinstance(raw_results, list):
        for item in raw_results:
            if isinstance(item, Mapping):
                port = _int_value(item.get("port"))
                if port is not None and 0 < port <= 65535:
                    values.append(port)
    return values


def _payload_services(payload: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("services", "protocols", "cpes"):
        raw = payload.get(key)
        if isinstance(raw, list):
            for item in raw:
                rendered = str(item or "").strip()
                if rendered:
                    values.append(rendered)
    raw_results = payload.get("results")
    if isinstance(raw_results, list):
        for item in raw_results:
            if isinstance(item, Mapping):
                rendered = str(item.get("service") or item.get("protocol") or "").strip()
                if rendered:
                    values.append(rendered)
    return values


def _certificate_expiry_from_payload(payload: Mapping[str, Any]) -> str:
    for key in ("latest_expiry", "not_after", "expires_at", "valid_to", "expiration", "expiry", "leaf_not_after"):
        value = _clean_date(payload.get(key))
        if value:
            return value
    for key in ("certificate", "cert", "tls"):
        nested = payload.get(key)
        if isinstance(nested, Mapping):
            value = _certificate_expiry_from_payload(nested)
            if value:
                return value
    certificates = payload.get("certificates")
    if isinstance(certificates, list):
        values = [
            value
            for item in certificates
            if isinstance(item, Mapping)
            and (value := _certificate_expiry_from_payload(item))
        ]
        return min(values) if values else ""
    return ""


def _clean_date(value: object) -> str:
    return str(value or "").strip().replace("Z", "+00:00")


def _days_until(value: str) -> int | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    return (parsed - datetime.now(timezone.utc)).days


def _is_past_datetime(value: object) -> bool:
    parsed = _parse_datetime(value)
    return parsed is not None and parsed < datetime.now(timezone.utc)


def _parse_datetime(value: object) -> datetime | None:
    rendered = _clean_date(value)
    if not rendered:
        return None
    try:
        parsed = datetime.fromisoformat(rendered)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(rendered)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _int_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None
