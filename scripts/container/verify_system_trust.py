#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Verify the Debian certifi exception against the actual runtime trust store."""

import hashlib
from pathlib import Path
import ssl


COMPROMISED_ROOT_SHA256 = "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"
SYSTEM_BUNDLE = Path("/etc/ssl/certs/ca-certificates.crt")


def verify_roots(certificates: list[bytes]) -> None:
    if not certificates:
        raise ValueError("System certificate store is empty")
    if any(hashlib.sha256(cert).hexdigest() == COMPROMISED_ROOT_SHA256 for cert in certificates):
        raise ValueError("System certificate store trusts the compromised emSign G3 root")


def main() -> None:
    # Run with /usr/bin/python3: the distro's certifi is distinct from pip's.
    import certifi

    if Path(certifi.where()) != SYSTEM_BUNDLE or certifi.contents() != SYSTEM_BUNDLE.read_text(encoding="ascii"):
        raise ValueError("Debian certifi no longer delegates to the reviewed system bundle")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=str(SYSTEM_BUNDLE))
    verify_roots(context.get_ca_certs(binary_form=True))
    print("Verified Debian certifi uses the system bundle without the compromised emSign G3 root")


if __name__ == "__main__":
    main()
