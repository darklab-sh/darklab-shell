# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Fixed Interactsh registration and encrypted polling transport."""

from __future__ import annotations

import json
from collections.abc import Mapping

from services.connectors.oast_config import OastConnectorSettings
from services.connectors.oast_provider_contracts import (
    OastProviderPollBatch,
    OastProviderSession,
    OastProviderTransportError,
)
from services.connectors.oast_provider_crypto import (
    decrypt_interaction,
    decrypt_poll_key,
    new_oast_provider_session,
    registration_public_key,
)
from services.connectors.oast_provider_http import request_oast_provider_bytes
from services.connectors.oast_provider_normalization import (
    normalize_oast_provider_interaction,
)


_MAX_CONTROL_BYTES = 4096
_MAX_POLL_BYTES = 1048576
_MAX_POLL_ITEMS = 128
_MAX_RETURNED_ITEMS = 64
_MAX_ENCRYPTED_ITEM_CHARS = 131072


def _json_object(payload: bytes) -> Mapping[str, object]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OastProviderTransportError(
            "oast_provider_response_invalid",
            "The private OAST provider returned invalid JSON",
        ) from exc
    if not isinstance(value, Mapping):
        raise OastProviderTransportError(
            "oast_provider_response_invalid",
            "The private OAST provider returned an invalid response",
        )
    return value


def register_oast_provider_session(
    settings: OastConnectorSettings,
    token: str,
    callback_label: str,
) -> OastProviderSession:
    """Register one generated client session for an app-approved callback label."""
    session = new_oast_provider_session(callback_label)
    response = _json_object(
        request_oast_provider_bytes(
            settings,
            token,
            "/register",
            method="POST",
            body={
                "public-key": registration_public_key(session),
                "secret-key": session.secret_key,
                "correlation-id": session.correlation_id,
            },
            max_bytes=_MAX_CONTROL_BYTES,
        )
    )
    if response != {"message": "registration successful"}:
        raise OastProviderTransportError(
            "oast_provider_registration_rejected",
            "The private OAST provider didn't confirm registration",
        )
    return session


def _poll_lists(response: Mapping[str, object]) -> tuple[list[str], int]:
    if not {"data", "extra", "aes_key"}.issubset(response) or set(response) - {
        "data",
        "extra",
        "aes_key",
        "tlddata",
    }:
        raise OastProviderTransportError(
            "oast_provider_response_invalid",
            "The private OAST provider returned an invalid poll response",
        )
    values: list[list[str]] = []
    for name in ("data", "extra", "tlddata"):
        raw_value = response.get(name, [])
        if raw_value is None:
            values.append([])
            continue
        if not isinstance(raw_value, list):
            raise OastProviderTransportError(
                "oast_provider_response_invalid",
                "The private OAST provider returned an invalid poll response",
            )
        if len(raw_value) > _MAX_POLL_ITEMS or any(
            not isinstance(item, str) or len(item) > _MAX_ENCRYPTED_ITEM_CHARS
            for item in raw_value
        ):
            raise OastProviderTransportError(
                "oast_provider_response_too_large",
                "The private OAST provider returned too many interactions",
            )
        values.append(raw_value)
    return values[0], len(values[1]) + len(values[2])


def poll_oast_provider_session(
    settings: OastConnectorSettings,
    token: str,
    session: OastProviderSession,
) -> OastProviderPollBatch:
    """Poll and decrypt only records for the registered callback identity."""
    response = _json_object(
        request_oast_provider_bytes(
            settings,
            token,
            "/poll",
            method="GET",
            query={"id": session.correlation_id, "secret": session.secret_key},
            max_bytes=_MAX_POLL_BYTES,
        )
    )
    encrypted, ignored_shared = _poll_lists(response)
    if not encrypted:
        return OastProviderPollBatch((), 0, ignored_shared)
    key = decrypt_poll_key(session, response.get("aes_key"))
    interactions: list[dict[str, object]] = []
    rejected_count = 0
    for value in encrypted:
        try:
            raw = decrypt_interaction(key, value)
        except OastProviderTransportError:
            rejected_count += 1
            continue
        normalized = normalize_oast_provider_interaction(raw, session, settings)
        if normalized is None or len(interactions) >= _MAX_RETURNED_ITEMS:
            rejected_count += 1
            continue
        interactions.append(normalized)
    return OastProviderPollBatch(
        tuple(interactions),
        rejected_count,
        ignored_shared,
    )


def deregister_oast_provider_session(
    settings: OastConnectorSettings,
    token: str,
    session: OastProviderSession,
) -> None:
    """Remove one provider registration without returning session secrets."""
    response = _json_object(
        request_oast_provider_bytes(
            settings,
            token,
            "/deregister",
            method="POST",
            body={
                "correlation-id": session.correlation_id,
                "secret-key": session.secret_key,
            },
            max_bytes=_MAX_CONTROL_BYTES,
        )
    )
    if response != {"message": "deregistration successful"}:
        raise OastProviderTransportError(
            "oast_provider_deregistration_rejected",
            "The private OAST provider didn't confirm deregistration",
        )


__all__ = [
    "OastProviderPollBatch",
    "OastProviderSession",
    "OastProviderTransportError",
    "deregister_oast_provider_session",
    "new_oast_provider_session",
    "poll_oast_provider_session",
    "register_oast_provider_session",
]
