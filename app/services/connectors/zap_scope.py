# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Target-scope review for the optional ZAP connector."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from services.connectors.zap_config import ZapConnectorSettings
from services.connectors.zap_url_scope import ZapUrlScopeError, review_target_url

_MAX_RESOLVED_ADDRESSES = 16


class ZapTargetScopeError(ValueError):
    """Raised when a target can't safely cross the ZAP connector boundary."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ReviewedZapTarget:
    url: str
    host: str
    resolved_addresses: tuple[str, ...]


def _system_resolve_addresses(host: str) -> Iterable[str]:
    for result in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM):
        yield str(result[4][0])


def review_zap_target(
    url: str,
    settings: ZapConnectorSettings,
    *,
    resolve_addresses: Callable[[str], Iterable[str]] = _system_resolve_addresses,
) -> ReviewedZapTarget:
    """Review one URL immediately before it is supplied to external ZAP."""
    if not settings.enabled:
        raise ZapTargetScopeError("zap_connector_disabled", "ZAP connector is disabled")
    try:
        candidate, host = review_target_url(url)
    except (ZapUrlScopeError, ValueError) as exc:
        raise ZapTargetScopeError("zap_target_invalid", str(exc)) from exc
    try:
        literal = ipaddress.ip_address(host)
        raw_addresses: Iterable[str] = (str(literal),)
    except ValueError:
        try:
            raw_addresses = resolve_addresses(host)
        except OSError as exc:
            raise ZapTargetScopeError(
                "zap_target_resolution_failed",
                "ZAP target hostname could not be resolved",
            ) from exc

    addresses: list[str] = []
    try:
        for raw_address in raw_addresses:
            address = str(ipaddress.ip_address(str(raw_address)))
            if address in addresses:
                continue
            addresses.append(address)
            if len(addresses) > _MAX_RESOLVED_ADDRESSES:
                raise ZapTargetScopeError(
                    "zap_target_resolution_limit",
                    "ZAP target resolved to too many addresses",
                )
    except ZapTargetScopeError:
        raise
    except OSError as exc:
        raise ZapTargetScopeError(
            "zap_target_resolution_failed",
            "ZAP target hostname could not be resolved",
        ) from exc
    except ValueError as exc:
        raise ZapTargetScopeError(
            "zap_target_resolution_invalid",
            "ZAP target resolution returned an invalid address",
        ) from exc
    if not addresses:
        raise ZapTargetScopeError(
            "zap_target_resolution_failed",
            "ZAP target hostname did not resolve to an address",
        )

    networks = tuple(ipaddress.ip_network(cidr) for cidr in settings.allowed_target_cidrs)
    if not networks or any(
        not any(ipaddress.ip_address(address) in network for network in networks)
        for address in addresses
    ):
        raise ZapTargetScopeError(
            "zap_target_out_of_scope",
            "ZAP target resolved outside the configured target networks",
        )
    return ReviewedZapTarget(
        url=candidate,
        host=host,
        resolved_addresses=tuple(addresses),
    )
