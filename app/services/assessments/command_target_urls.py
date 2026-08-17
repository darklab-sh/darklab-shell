# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""URL formatting shared by bounded Assessment command planners."""

from __future__ import annotations

import ipaddress


def default_https_target(target_type: str, target_value: str) -> str:
    """Return one HTTPS target with an IPv6 literal formatted as a URL host."""
    if target_type == "url":
        return target_value
    host = target_value
    if target_type == "ip":
        try:
            address = ipaddress.ip_address(target_value)
        except ValueError:
            return f"https://{target_value}"
        host = f"[{address}]" if address.version == 6 else str(address)
    return f"https://{host}"


__all__ = ["default_https_target"]
