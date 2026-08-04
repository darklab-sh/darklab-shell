# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Input-shape helpers shared by Atlas entry points."""

from ipaddress import ip_network


def is_ip_network_range(value: str) -> bool:
    token = str(value or "").strip()
    if "/" not in token:
        return False
    try:
        ip_network(token, strict=False)
    except ValueError:
        return False
    return True
