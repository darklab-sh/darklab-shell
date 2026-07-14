# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Compatibility exports for the shared diff classifier registry."""

from services.diff.classifiers import (  # noqa: F401
    AppliesFunc,
    DiffClassifier,
    DiffFunc,
    WatcherClassifier,
    diff_with_classifiers,
    register_classifier,
    registered_classifiers,
)
