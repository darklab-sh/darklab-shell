# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared diff classifier registry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from services.diff.models import DiffResult

AppliesFunc = Callable[[str, dict[str, Any], Any | None], bool]
DiffFunc = Callable[[dict[str, Any], dict[str, Any], dict[str, bool] | None, Any | None], DiffResult]


@dataclass(frozen=True)
class DiffClassifier:
    name: str
    applies_to: AppliesFunc
    diff: DiffFunc


WatcherClassifier = DiffClassifier

_CLASSIFIERS: list[DiffClassifier] = []
_BUILTINS_REGISTERED = False
_CLASSIFIER_PRIORITY = {
    "findings": 0,
    "ports": 10,
    "hosts": 20,
    "tls": 30,
    "textual": 10_000,
}


def register_classifier(name: str, *, applies_to: AppliesFunc):
    """Register a shared diff classifier in priority order."""
    normalized = str(name or "").strip()
    if not normalized:
        raise ValueError("diff classifier name is required")

    def _decorator(diff_func: DiffFunc):
        _CLASSIFIERS.append(DiffClassifier(normalized, applies_to, diff_func))
        return diff_func

    return _decorator


def registered_classifiers() -> list[DiffClassifier]:
    _register_builtins_once()
    return _ordered_classifiers()


def diff_with_classifiers(
    baseline_run: dict[str, Any],
    current_run: dict[str, Any],
    *,
    options: dict[str, bool] | None = None,
    conn=None,
) -> DiffResult:
    _register_builtins_once()
    command_text = str(current_run.get("command") or baseline_run.get("command") or "")
    for classifier in _ordered_classifiers():
        if classifier.applies_to(command_text, current_run, conn):
            return classifier.diff(baseline_run, current_run, options, conn)
    raise RuntimeError("textual fallback classifier was not registered")


def _register_builtins_once() -> None:
    global _BUILTINS_REGISTERED
    if _BUILTINS_REGISTERED:
        return
    from services.diff.classifiers import findings, ports, hosts, tls, textual  # noqa: F401, PLC0415

    _BUILTINS_REGISTERED = True


def _ordered_classifiers() -> list[DiffClassifier]:
    return sorted(
        _CLASSIFIERS,
        key=lambda classifier: (_CLASSIFIER_PRIORITY.get(classifier.name, 5_000), classifier.name),
    )
