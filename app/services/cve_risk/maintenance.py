# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Post-schema maintenance registration for CVE risk state."""

from collections.abc import Callable, Mapping
from typing import Any

from .bootstrap import load_bundled_snapshots
from .links import sync_finding_cve_links
from .nvd_advisory import load_configured_local_nvd
from .osv_acquisition import load_configured_local_osv


def run_cve_risk_maintenance(
    conn: Any,
    run_step: Callable[[str, Callable[[], Any]], None],
    cfg: Mapping[str, Any],
) -> None:
    raw = cfg.get("cve_risk")
    settings = raw if isinstance(raw, Mapping) else {}
    if bool(settings.get("bootstrap_enabled", True)):
        run_step("cve_risk_bootstrap", lambda: load_bundled_snapshots(conn))
    if str(settings.get("advisory_mode") or "disabled").lower() == "local":
        run_step("cve_advisory_local_nvd", lambda: load_configured_local_nvd(conn, cfg=cfg))
    if str(settings.get("osv_advisory_mode") or "disabled").lower() == "local":
        run_step("cve_advisory_local_osv", lambda: load_configured_local_osv(conn, cfg=cfg))
    run_step("finding_cve_link_backfill", lambda: sync_finding_cve_links(conn))
