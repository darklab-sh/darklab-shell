# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Remove archives stopped by authorization without exposing their contents or paths."""

from __future__ import annotations

import logging
from pathlib import Path
import re

from services.auth.observability import _request_value

log = logging.getLogger("shell")
_JOB_ID_RE = re.compile(r"^(?:epj|rpj)_[a-f0-9]{24}$")
_STAGES = {"progress_authorization", "post_build_authorization", "retention_authorization", "discard_authorization"}


def remove_revoked_archive(path: str, *, job_id: str, job_kind: str, stage: str) -> bool:
    """Return whether the archive is gone; callers retain retry metadata on failure."""
    try:
        Path(path).unlink()
    except FileNotFoundError:
        return True
    except OSError as exc:
        log.warning("EXPORT_REVOKED_ARCHIVE_CLEANUP_FAILED", extra={
            "job_id": job_id if _JOB_ID_RE.fullmatch(job_id) else "",
            "job_kind": job_kind if job_kind in {"package", "report"} else "unknown",
            "stage": stage if stage in _STAGES else "unknown",
            "error_type": _request_value(type(exc).__name__, 80),
            "errno": exc.errno if isinstance(exc.errno, int) else None,
        })
        return False
    return True
