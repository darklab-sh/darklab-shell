# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Manifest reuse follows app ownership and actual file changes."""

import json
import os
from unittest import mock

import pytest
from flask import Flask

import app as shell


def _write(path, name):
    path.write_text(json.dumps({"bundles": {name: {"type": "js"}}}), encoding="utf-8")


def test_manifest_cache_reuses_valid_reads_and_invalidates_edits_and_replacements(tmp_path, monkeypatch):
    path = tmp_path / "manifest.json"
    _write(path, "old")
    monkeypatch.setattr(shell, "_ASSET_MANIFEST_PATH", path)
    previous = path.stat()
    stat = type(path).stat
    # Exercise a filesystem whose metadata cannot distinguish same-sized edits.
    monkeypatch.setattr(type(path), "stat", lambda target, **kwargs: previous if target == path else stat(target, **kwargs))
    app = Flask(__name__)
    with app.app_context(), mock.patch.object(shell.json, "loads", wraps=json.loads) as load:
        assert "old" in shell._load_asset_manifest()["bundles"]
        assert "old" in shell._load_asset_manifest()["bundles"]
        assert load.call_count == 1
        _write(path, "new")
        os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
        assert "new" in shell._load_asset_manifest()["bundles"]
        replacement = tmp_path / "replacement.json"
        _write(replacement, "end")
        os.utime(replacement, ns=(previous.st_atime_ns, previous.st_mtime_ns))
        replacement.replace(path)
        assert "end" in shell._load_asset_manifest()["bundles"]
        assert load.call_count == 3


def test_manifest_cache_is_scoped_to_app_and_path(tmp_path, monkeypatch):
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    _write(first, "first")
    _write(second, "second")
    monkeypatch.setattr(shell, "_ASSET_MANIFEST_PATH", first)
    app = Flask("first")
    with app.app_context():
        shell._load_asset_manifest()["bundles"]["first"]["type"] = "mutated"
    with Flask("second").app_context():
        assert shell._load_asset_manifest()["bundles"]["first"]["type"] == "js"
    with app.app_context():
        monkeypatch.setattr(shell, "_ASSET_MANIFEST_PATH", second)
        assert set(shell._load_asset_manifest()["bundles"]) == {"second"}
    # Non-Flask callers don't retain mutable shared state either.
    shell._load_asset_manifest()["bundles"].clear()
    assert set(shell._load_asset_manifest()["bundles"]) == {"second"}


@pytest.mark.parametrize("broken", [None, "{", "[]", "{}"])
def test_cached_manifest_does_not_mask_missing_or_invalid_files(tmp_path, monkeypatch, broken):
    path = tmp_path / "manifest.json"
    _write(path, "good")
    monkeypatch.setattr(shell, "_ASSET_MANIFEST_PATH", path)
    with Flask(__name__).app_context():
        assert "good" in shell._load_asset_manifest()["bundles"]
        if broken is None:
            path.unlink()
        else:
            path.write_text(broken, encoding="utf-8")
        with pytest.raises(RuntimeError, match="Run assets:sync"):
            shell._load_asset_manifest()
        _write(path, "fixed")
        assert "fixed" in shell._load_asset_manifest()["bundles"]
