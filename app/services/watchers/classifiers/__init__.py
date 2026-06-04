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
