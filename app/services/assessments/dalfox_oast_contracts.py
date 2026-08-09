# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Stable identity for the reviewed blind-XSS OAST assessment action."""


DALFOX_OAST_VALIDATION_CHECK_KEY = "blind_xss_validation"
DALFOX_OAST_ACTION_KEY = "oast_private_callback"


__all__ = [
    "DALFOX_OAST_ACTION_KEY",
    "DALFOX_OAST_VALIDATION_CHECK_KEY",
]
