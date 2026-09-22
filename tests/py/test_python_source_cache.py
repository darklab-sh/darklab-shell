# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Repository analysis caches preserve fresh-source and visitor isolation contracts."""

import ast
import os

import pytest

from python_source import PythonSourceCache


def _assigned_constant(tree: ast.Module) -> ast.Constant:
    statement = tree.body[0]
    assert isinstance(statement, ast.Assign)
    assert isinstance(statement.value, ast.Constant)
    return statement.value


def test_cached_syntax_is_independent_and_invalidates_same_metadata_edits(tmp_path):
    path = tmp_path / "sample.py"
    path.write_text("answer = 1\n")
    cache = PythonSourceCache()
    original = cache.parse(path)
    _assigned_constant(original).value = 999
    second = cache.parse(path)
    assert _assigned_constant(second).value == 1
    second.body.clear()
    assert len(cache.parse(path).body) == 1
    stamp = path.stat()
    path.write_text("answer = 2\n")
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert _assigned_constant(cache.parse(path)).value == 2
    peer = tmp_path / "other" / path.name
    peer.parent.mkdir()
    peer.write_text("answer = 3\n")
    assert _assigned_constant(cache.parse(peer)).value == 3
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
