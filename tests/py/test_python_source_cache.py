# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Repository analysis caches preserve fresh-source and visitor isolation contracts."""

import ast
import os

import pytest

from python_source import PythonSourceCache


def test_cached_syntax_is_independent_and_invalidates_same_metadata_edits(tmp_path):
    path = tmp_path / "sample.py"
    path.write_text("answer = 1\n")
    cache = PythonSourceCache()
    original = cache.parse(path)
    original.body[0].value.value = 999
    second = cache.parse(path)
    assert second.body[0].value.value == 1
    second.body.clear()
    assert len(cache.parse(path).body) == 1
    stamp = path.stat()
    path.write_text("answer = 2\n")
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert cache.parse(path).body[0].value.value == 2
    peer = tmp_path / "other" / path.name
    peer.parent.mkdir()
    peer.write_text("answer = 3\n")
    assert cache.parse(peer).body[0].value.value == 3
    path.write_text("answer =\n")
    with pytest.raises(SyntaxError) as error:
        cache.parse(path, filename="reviewed/sample.py")
    assert error.value.filename == "reviewed/sample.py" and error.value.lineno == 1
    path.unlink()
    with pytest.raises(FileNotFoundError):
        cache.parse(path)


def test_cache_eviction_and_oversized_files_preserve_analysis(tmp_path):
    path = tmp_path / "one.py"
    path.write_text("one = 1\n")
    cache = PythonSourceCache()
    expected = ast.dump(cache.parse(path))
    cache.max_bytes = cache.size
    peer = tmp_path / "two.py"
    peer.write_text("two = 2\n")
    cache.parse(peer)
    assert len(cache.entries) == 1 and cache.size <= cache.max_bytes
    assert ast.dump(cache.parse(path)) == expected
    uncached = PythonSourceCache(max_bytes=0)
    assert ast.dump(uncached.parse(path)) == expected
    assert uncached.size == 0 and not uncached.entries
