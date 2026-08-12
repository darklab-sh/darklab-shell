# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Stable execution modes derived from saved assessment commands."""

from __future__ import annotations

from core.output_targets import tokenize_command
from services.assessments.command_modes_dalfox import (
    DALFOX_OAST_VALIDATION_MODE,
    DALFOX_PARAMETER_DISCOVERY_MODE,
    DALFOX_XSS_VALIDATION_MODE,
    dalfox_command_mode,
)
from services.assessments.command_modes_nuclei import (
    NUCLEI_INTRUSIVE_PROFILE_MODE,
    NUCLEI_SAFE_PROFILE_MODE,
    NUCLEI_STANDARD_PROFILE_MODE,
    nuclei_command_mode,
)
from services.assessments.command_modes_tls import (
    TLS_CERTIFICATE_CHAIN_MODE,
    TLS_CONFIGURATION_MODE,
    tls_command_mode,
)


ASSESSMENT_COMMAND_MODES = frozenset({
    DALFOX_OAST_VALIDATION_MODE,
    DALFOX_PARAMETER_DISCOVERY_MODE,
    DALFOX_XSS_VALIDATION_MODE,
    NUCLEI_SAFE_PROFILE_MODE,
    NUCLEI_STANDARD_PROFILE_MODE,
    NUCLEI_INTRUSIVE_PROFILE_MODE,
    TLS_CERTIFICATE_CHAIN_MODE,
    TLS_CONFIGURATION_MODE,
})


def assessment_command_mode(command: object) -> str:
    """Return one frozen mode only for a maintained assessment command shape."""
    tokens = tokenize_command(str(command or ""))
    if len(tokens) < 2:
        return ""
    if tokens[0].casefold() == "nuclei":
        return nuclei_command_mode(tokens)
    if tokens[0].casefold() == "dalfox":
        return dalfox_command_mode(tokens)
    if tokens[0].casefold() in {"sslyze", "testssl"}:
        return tls_command_mode(tokens)
    return ""


__all__ = [
    "ASSESSMENT_COMMAND_MODES",
    "DALFOX_OAST_VALIDATION_MODE",
    "DALFOX_PARAMETER_DISCOVERY_MODE",
    "DALFOX_XSS_VALIDATION_MODE",
    "NUCLEI_INTRUSIVE_PROFILE_MODE",
    "NUCLEI_SAFE_PROFILE_MODE",
    "NUCLEI_STANDARD_PROFILE_MODE",
    "TLS_CERTIFICATE_CHAIN_MODE",
    "TLS_CONFIGURATION_MODE",
    "assessment_command_mode",
]
