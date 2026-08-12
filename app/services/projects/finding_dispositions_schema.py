# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared table inventory for finding remediation state."""

SHARED_TABLES: tuple[str, ...] = (
    "finding_remediation_dispositions",
    "finding_remediation_merge_members",
)
