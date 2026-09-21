# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded, process-local syntax cache for repository analysis tools."""

import ast
from collections import OrderedDict
import hashlib
from pathlib import Path
import pickle


class PythonSourceCache:
    def __init__(self, max_bytes=64 * 1024 * 1024):
        self.max_bytes = max_bytes
        self.size = 0
        self.entries = OrderedDict()

    def parse(self, path: Path, *, filename=None) -> ast.Module:
        source = path.read_text(encoding="utf-8")
        key = path.resolve()
        digest = hashlib.sha256(source.encode("utf-8")).digest()
        previous = self.entries.pop(key, None)
        if previous:
            self.size -= len(previous[1])
            if previous[0] == digest:
                self.entries[key] = previous
                self.size += len(previous[1])
                # Only bytes serialized in this process enter the cache. Each
                # visitor gets independent nodes, including mutable child lists.
                return pickle.loads(previous[1])  # noqa: S301
        tree = ast.parse(source, filename=filename or str(path))
        payload = pickle.dumps(tree, protocol=pickle.HIGHEST_PROTOCOL)
        if len(payload) <= self.max_bytes:
            while self.size + len(payload) > self.max_bytes:
                _, (_, removed) = self.entries.popitem(last=False)
                self.size -= len(removed)
            self.entries[key] = (digest, payload)
            self.size += len(payload)
        return tree


_SOURCE_CACHE = PythonSourceCache()
parse_python_source = _SOURCE_CACHE.parse
