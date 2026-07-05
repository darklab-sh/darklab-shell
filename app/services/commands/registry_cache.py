"""Read-only containers for cached command registry data."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, NoReturn, SupportsIndex


def _raise_read_only_registry() -> NoReturn:
    raise TypeError("cached command registry is read-only")


class FrozenDict(dict):
    """A dict-shaped read-only container for cached registry data."""

    def __setitem__(self, key, value):
        _raise_read_only_registry()

    def __delitem__(self, key):
        _raise_read_only_registry()

    def clear(self):
        _raise_read_only_registry()

    def pop(self, key, default=None):
        _raise_read_only_registry()

    def popitem(self):
        _raise_read_only_registry()

    def setdefault(self, key, default=None):
        _raise_read_only_registry()

    def update(self, *args, **kwargs):
        _raise_read_only_registry()

    def __ior__(self, other):
        _raise_read_only_registry()

    def __deepcopy__(self, memo):
        copied = {}
        memo[id(self)] = copied
        for key, value in self.items():
            copied[deepcopy(key, memo)] = deepcopy(value, memo)
        return copied


class FrozenList(list):
    """A list-shaped read-only container for cached registry data."""

    def __setitem__(self, key, value):
        _raise_read_only_registry()

    def __delitem__(self, key):
        _raise_read_only_registry()

    def __iadd__(self, other):
        _raise_read_only_registry()

    def __imul__(self, other):
        _raise_read_only_registry()

    def append(self, item):
        _raise_read_only_registry()

    def clear(self):
        _raise_read_only_registry()

    def extend(self, other):
        _raise_read_only_registry()

    def insert(self, index, item):
        _raise_read_only_registry()

    def pop(self, index: SupportsIndex = -1):
        _raise_read_only_registry()

    def remove(self, item):
        _raise_read_only_registry()

    def reverse(self):
        _raise_read_only_registry()

    def sort(self, *args, **kwargs):
        _raise_read_only_registry()

    def __deepcopy__(self, memo):
        copied = []
        memo[id(self)] = copied
        copied.extend(deepcopy(item, memo) for item in self)
        return copied


def freeze_registry_value(value: Any) -> Any:
    if isinstance(value, (FrozenDict, FrozenList)):
        return value
    if isinstance(value, dict):
        return FrozenDict({
            key: freeze_registry_value(item)
            for key, item in value.items()
        })
    if isinstance(value, list):
        return FrozenList(freeze_registry_value(item) for item in value)
    return value
