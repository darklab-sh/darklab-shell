# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project Overview compatibility wrappers for shared Intel evidence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.atlas.intel_evidence import (
    CERT_STATUS_EXPIRED as CERT_STATUS_EXPIRED,
    CERT_STATUS_EXPIRING_14D as CERT_STATUS_EXPIRING_14D,
    CERT_STATUS_EXPIRING_30D as CERT_STATUS_EXPIRING_30D,
    CERT_STATUS_HEALTHY as CERT_STATUS_HEALTHY,
    CERT_STATUS_ORDER as CERT_STATUS_ORDER,
    CERT_STATUS_UNKNOWN as CERT_STATUS_UNKNOWN,
    classify_certificate_status as classify_certificate_status,
    extract_intel_evidence,
)


def _overview_intel_extract(
    snapshots: list[dict[str, Any]],
    *,
    entity_id: str = "",
    log_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return extract_intel_evidence(
        snapshots,
        entity_id=entity_id,
        log_context=log_context,
        log_event_namespace="PROJECT_OVERVIEW",
    )
