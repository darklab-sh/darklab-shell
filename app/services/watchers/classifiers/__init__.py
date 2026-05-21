"""Watcher diff classifier registry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from services.watchers.models import WatcherDiff

AppliesFunc = Callable[[str, dict[str, Any], Any | None], bool]
DiffFunc = Callable[[dict[str, Any], dict[str, Any], dict[str, bool] | None, Any | None], WatcherDiff]


@dataclass(frozen=True)
class WatcherClassifier:
    name: str
    applies_to: AppliesFunc
    diff: DiffFunc


_CLASSIFIERS: list[WatcherClassifier] = []
_BUILTINS_REGISTERED = False


def register_classifier(name: str, *, applies_to: AppliesFunc):
    """Register a watcher classifier in priority order."""
    normalized = str(name or "").strip()
    if not normalized:
        raise ValueError("watcher classifier name is required")

    def _decorator(diff_func: DiffFunc):
        _CLASSIFIERS.append(WatcherClassifier(normalized, applies_to, diff_func))
        return diff_func

    return _decorator


def registered_classifiers() -> list[WatcherClassifier]:
    _register_builtins_once()
    return list(_CLASSIFIERS)


def diff_with_classifiers(
    baseline_run: dict[str, Any],
    current_run: dict[str, Any],
    *,
    options: dict[str, bool] | None = None,
    conn=None,
) -> WatcherDiff:
    _register_builtins_once()
    command_text = str(current_run.get("command") or baseline_run.get("command") or "")
    for classifier in _CLASSIFIERS:
        if classifier.applies_to(command_text, current_run, conn):
            return classifier.diff(baseline_run, current_run, options, conn)
    raise RuntimeError("watcher textual fallback classifier was not registered")


def _register_builtins_once() -> None:
    global _BUILTINS_REGISTERED
    if _BUILTINS_REGISTERED:
        return
    from services.watchers.classifiers import findings, ports, hosts, tls, textual  # noqa: F401, PLC0415
    _BUILTINS_REGISTERED = True
