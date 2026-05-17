"""Filesystem-backed storage for large database text bodies."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
from typing import Any

from config import resolve_data_dir

DATA_DIR = resolve_data_dir()
BODY_STORE_DIR = os.path.join(DATA_DIR, "body-store")

_POINTER_KEY = "__darklab_body_store__"
_POINTER_VERSION = 1
_SAFE_TOKEN_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _safe_token(value: str) -> str:
    token = _SAFE_TOKEN_RE.sub("-", str(value).strip()).strip(".-")
    return token[:96] or "body"


def _encode_pointer(pointer: dict[str, Any]) -> str:
    return json.dumps(pointer, separators=(",", ":"), sort_keys=True)


def _decode_pointer(value: str | dict[str, Any] | None) -> dict[str, Any] | None:
    if not value:
        return None
    if isinstance(value, dict):
        parsed = value
    else:
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return None
    if not isinstance(parsed, dict):
        return None
    if parsed.get(_POINTER_KEY) != _POINTER_VERSION:
        return None
    rel_path = parsed.get("rel_path")
    if not isinstance(rel_path, str) or not rel_path:
        return None
    return parsed


def _body_path(rel_path: str) -> str:
    root = os.path.abspath(DATA_DIR)
    path = os.path.abspath(os.path.join(DATA_DIR, rel_path))
    if path != root and not path.startswith(root + os.sep):
        raise ValueError("Stored body path escaped data directory")
    return path


def _preview_text(text: str, max_chars: int = 4096) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def inline_threshold_bytes(value: Any) -> int:
    """Return a non-negative byte threshold from forgiving config input."""
    if value is None or isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str):
        token = value.strip().lower().replace(" ", "")
        multiplier = 1
        if token.endswith("kb"):
            token = token[:-2]
            multiplier = 1024
        elif token.endswith("k"):
            token = token[:-1]
            multiplier = 1024
        elif token.endswith("mb"):
            token = token[:-2]
            multiplier = 1024 * 1024
        elif token.endswith("m"):
            token = token[:-1]
            multiplier = 1024 * 1024
        if not token:
            return 0
        try:
            return max(0, int(float(token) * multiplier))
        except ValueError:
            return 0
    return 0


def maybe_store_text_body(
    kind: str,
    owner_id: str,
    text: str,
    threshold_bytes: Any,
    *,
    preview_chars: int = 4096,
) -> str:
    """Return inline text or a JSON pointer to a compressed body file."""
    body = str(text or "")
    encoded = body.encode("utf-8")
    threshold = inline_threshold_bytes(threshold_bytes)
    if threshold <= 0 or len(encoded) <= threshold:
        return body

    digest = hashlib.sha256(encoded).hexdigest()
    safe_kind = _safe_token(kind)
    safe_owner = _safe_token(owner_id)
    rel_path = os.path.join("body-store", safe_kind, f"{safe_owner}-{digest[:16]}.txt.gz")
    abs_path = _body_path(rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with gzip.open(abs_path, "wt", encoding="utf-8") as handle:
        handle.write(body)
    return _encode_pointer({
        _POINTER_KEY: _POINTER_VERSION,
        "kind": safe_kind,
        "rel_path": rel_path,
        "byte_size": len(encoded),
        "sha256": digest,
        "preview": _preview_text(body, preview_chars),
    })


def stored_body_pointer(value: str | dict[str, Any] | None) -> dict[str, Any] | None:
    return _decode_pointer(value)


def load_text_body(value: str | dict[str, Any] | None, *, fallback_to_preview: bool = True) -> str:
    pointer = _decode_pointer(value)
    if pointer is None:
        return str(value or "")
    try:
        with gzip.open(_body_path(str(pointer["rel_path"])), "rt", encoding="utf-8") as handle:
            body = handle.read()
    except OSError:
        if fallback_to_preview:
            return str(pointer.get("preview") or "")
        raise
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if pointer.get("sha256") and digest != pointer.get("sha256"):
        raise ValueError("Stored body checksum mismatch")
    return body


def delete_text_body(value: str | dict[str, Any] | None) -> None:
    pointer = _decode_pointer(value)
    if pointer is None:
        return
    try:
        os.remove(_body_path(str(pointer["rel_path"])))
    except FileNotFoundError:
        pass
